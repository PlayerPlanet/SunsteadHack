"""Story D Phase-1 tests — backend wiring, MCP tool surface, CLI adapter.

All offline: no database. The in-memory backend is used unless CLEANROOM_PG_DSN is
set; the Postgres-selection test fakes the `from_dsn` constructors so it never
connects. The end-to-end DOD flow (register -> escalation -> adjudicate -> dispatch
-> curve) runs against the cached in-memory singletons within one process.
"""

import json
import time

import pytest

from cleanroom.control.server import wiring
from cleanroom.control.server import mcp as mcpmod
from cleanroom.control.server import cli as climod
from cleanroom.control.registry.store import TaskRegistryStore


_SPEC = {
    "task_id": "d-phase1-demo",
    "objective": "minimize p99 on wl1",
    "workload_id": "wl1",
    "action_space": ["index"],
    "db_ref": "demo-db",
    "constraints": {"cost_budget": 1.0},
    "default_model": "claude-haiku-4-5-20251001",
}


@pytest.fixture(autouse=True)
def _isolated_backend(tmp_path, monkeypatch):
    """In-memory backend + a throwaway registry dir; reset cached singletons."""
    monkeypatch.delenv("CLEANROOM_PG_DSN", raising=False)
    tasks_dir = tmp_path / "tasks"
    monkeypatch.setattr(
        wiring, "TaskRegistryStore", lambda *a, **k: TaskRegistryStore(tasks_dir)
    )
    wiring.reset_caches()
    yield
    wiring.reset_caches()


# --------------------------- backend selection ---------------------------


def test_inmemory_selection_when_no_dsn():
    from cleanroom.control.dispatcher.store_interface import InMemoryRunStore
    from cleanroom.fixtures import InMemoryLogClient

    op = wiring.make_operator()
    assert isinstance(op.run_store, InMemoryRunStore)
    assert isinstance(wiring.make_logclient(), InMemoryLogClient)


def test_postgres_selection_when_dsn_set(monkeypatch):
    """With CLEANROOM_PG_DSN set, the Pg backends are chosen — without connecting."""
    monkeypatch.setenv("CLEANROOM_PG_DSN", "postgres://fake/db")
    wiring.reset_caches()

    import cleanroom.control.dispatcher.pg_store as pg
    import cleanroom.logclient as lc
    import cleanroom.db as db

    sentinel_store = object()
    sentinel_log = object()

    class _FakeConn:
        def close(self):
            pass

    monkeypatch.setattr(
        pg.PgRunStore, "from_dsn", classmethod(lambda cls, dsn, **k: sentinel_store)
    )
    monkeypatch.setattr(db, "connect", lambda dsn=None, **k: _FakeConn())
    monkeypatch.setattr(db, "init_schema", lambda conn: None)
    monkeypatch.setattr(
        lc.PgLogClient, "from_dsn", classmethod(lambda cls, dsn, **k: sentinel_log)
    )

    op = wiring.make_operator()
    assert op.run_store is sentinel_store
    assert wiring.make_logclient() is sentinel_log


# --------------------------- MCP DOD flow ---------------------------


def _await_terminal(run_id, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        st = mcpmod.tool_get_run(run_id)
        if st and st["state"] in ("done", "failed", "cancelled"):
            return st
        time.sleep(0.02)
    return mcpmod.tool_get_run(run_id)


def test_mcp_full_dod_flow():
    """register (governed) -> pending -> adjudicate approve -> dispatch -> curve."""
    # Defining a task is governed: the irreversible task_definition escalates.
    task_id = mcpmod.tool_register_task(json.dumps(_SPEC))
    assert task_id == "d-phase1-demo"

    # Not active until adjudicated.
    assert mcpmod.tool_get_task(task_id) is None
    assert all(t["task_id"] != task_id for t in mcpmod.tool_list_tasks())

    # Exactly one escalation, requiring human judgment.
    esc = mcpmod.tool_pending_escalations()
    assert len(esc) == 1
    assert esc[0]["requires_human_judgment"] is True
    crossing_id = esc[0]["id"]

    # Human approves -> task activates.
    mcpmod.tool_adjudicate(crossing_id, "approve", "meets safety bar", "human")
    activated = mcpmod.tool_get_task(task_id)
    assert activated is not None and activated["task_id"] == task_id

    # Dispatch is fire-and-return; run reaches a terminal state.
    run_id = mcpmod.tool_dispatch_run(task_id, "claude-haiku-4-5-20251001", 4)
    assert isinstance(run_id, str) and run_id
    st = _await_terminal(run_id)
    assert st["state"] == "done"

    # Run is visible via list_runs, and the curve has experiments.
    assert any(r["run_id"] == run_id for r in mcpmod.tool_list_runs())
    curve = mcpmod.tool_read_curve(task_id)
    assert len(curve) >= 1
    for exp in curve:
        assert exp["task_id"] == task_id
        assert exp["decision"] in {"keep", "discard", "rollback", "escalated"}


def test_mcp_reject_leaves_task_inactive():
    task_id = mcpmod.tool_register_task(json.dumps({**_SPEC, "task_id": "d-reject"}))
    crossing_id = mcpmod.tool_pending_escalations()[0]["id"]
    mcpmod.tool_adjudicate(crossing_id, "reject", "not now", "human")
    assert mcpmod.tool_get_task("d-reject") is None


def test_mcp_server_builds_with_ten_tools():
    import asyncio

    server = mcpmod.build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "list_tasks", "get_task", "register_task", "dispatch_run", "get_run",
        "list_runs", "cancel_run", "pending_escalations", "adjudicate", "read_curve",
    }


# --------------------------- CLI adapter ---------------------------


def test_cli_register_pending_curve(capsys):
    climod.main(["register-task", "--spec-json", json.dumps({**_SPEC, "task_id": "d-cli"})])
    out = capsys.readouterr().out
    assert "d-cli" in out

    climod.main(["pending-escalations"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload, list) and len(payload) >= 1

    # read-curve on a task with no experiments yet -> empty list (valid JSON).
    climod.main(["read-curve", "d-cli"])
    out = capsys.readouterr().out
    assert json.loads(out) == []
