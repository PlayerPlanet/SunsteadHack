"""Tests for the web/worker split: queue-mode dispatch, atomic claim, worker execution.

All offline (InMemoryRunStore + fixtures). The in-memory claim_next models the same
claim-and-transition contract PgRunStore implements with FOR UPDATE SKIP LOCKED.
"""

import pytest

import cleanroom.pore
from cleanroom.control.dispatcher.state import RunStatus
from cleanroom.control.dispatcher.store_interface import InMemoryRunStore
from cleanroom.control.ops import Operator, OperatorContext
from cleanroom.control.registry.types import TaskSpec
from cleanroom.control.server.auth import Principal
from cleanroom.control.server.context import current_principal
from cleanroom.control.server.roles import ROLE_READONLY
from cleanroom.control.worker import run_once, run_worker
from cleanroom.fixtures import CannedBenchmark, DummyProposer, InMemoryLogClient

_SPEC = TaskSpec(
    task_id="t1",
    objective="minimize p99",
    workload_id="wl1",
    action_space=["index"],
    db_ref="demo",
    constraints={"cost_budget": 1.0},
    default_model="claude-haiku-4-5-20251001",
)


class FakeRegistry:
    """Minimal registry exposing only what dispatch_run / the worker use: .get()."""

    def __init__(self, specs):
        self._specs = {s.task_id: s for s in specs}

    def get(self, task_id):
        return self._specs.get(task_id)


def _ctx(logclient):
    return OperatorContext(proposer=DummyProposer(), benchmark=CannedBenchmark(),
                           pore=cleanroom.pore, logclient=logclient)


def _queued(run_id, task_id="t1", target=4) -> RunStatus:
    return RunStatus(run_id, task_id, "m", "queued", 0, None, None, None, None, target)


# ---- queue-mode dispatch does NOT execute inline -----------------------------

def test_queue_mode_leaves_run_queued_without_running():
    store = InMemoryRunStore()
    log = InMemoryLogClient()
    op = Operator(FakeRegistry([_SPEC]), store)
    run_id = op.dispatch_run("t1", model="m", iterations=4, ctx=_ctx(log), mode="queue")

    st = store.get(run_id)
    assert st.state == "queued"
    assert st.iterations_target == 4
    assert log.read_experiments() == []  # nothing ran in the web process


def test_thread_mode_still_runs_inline():
    # Back-compat: default mode keeps the local stdio behavior (runs in this process).
    store = InMemoryRunStore()
    log = InMemoryLogClient()
    op = Operator(FakeRegistry([_SPEC]), store)
    run_id = op.dispatch_run("t1", model="m", iterations=4, ctx=_ctx(log), mode="thread")
    # daemon thread; poll briefly for terminal state
    import time
    for _ in range(250):
        if store.get(run_id).state in ("done", "failed", "cancelled"):
            break
        time.sleep(0.02)
    assert store.get(run_id).state == "done"


# ---- atomic claim ------------------------------------------------------------

def test_claim_next_claims_each_run_once():
    store = InMemoryRunStore()
    store.set("a", _queued("a"))
    store.set("b", _queued("b"))

    c1 = store.claim_next()
    c2 = store.claim_next()
    c3 = store.claim_next()

    assert {c1.run_id, c2.run_id} == {"a", "b"}
    assert c1.run_id != c2.run_id          # never the same run twice
    assert c1.state == "running"           # claimed -> running
    assert c3 is None                      # queue drained


def test_claim_next_skips_non_queued():
    store = InMemoryRunStore()
    store.set("done", RunStatus("done", "t1", "m", "done", 4, 1.0, None, None, None, 4))
    assert store.claim_next() is None


# ---- worker executes a claimed run ------------------------------------------

def test_run_once_executes_queued_run_to_done():
    store = InMemoryRunStore()
    log = InMemoryLogClient()
    op = Operator(FakeRegistry([_SPEC]), store)
    run_id = op.dispatch_run("t1", model="m", iterations=4, ctx=_ctx(log), mode="queue")

    processed = run_once(run_store=store, registry=FakeRegistry([_SPEC]),
                         ctx_factory=lambda: _ctx(log))
    assert processed == run_id
    st = store.get(run_id)
    assert st.state == "done"
    assert st.iterations_done >= 1
    assert len(log.read_experiments()) >= 1  # the worker, not the web tier, ran the loop


def test_run_once_returns_none_on_empty_queue():
    store = InMemoryRunStore()
    assert run_once(run_store=store, registry=FakeRegistry([_SPEC]),
                    ctx_factory=lambda: _ctx(InMemoryLogClient())) is None


def test_run_once_fails_run_when_task_missing():
    store = InMemoryRunStore()
    store.set("ghost", _queued("ghost", task_id="nope"))
    processed = run_once(run_store=store, registry=FakeRegistry([]),
                         ctx_factory=lambda: _ctx(InMemoryLogClient()))
    assert processed == "ghost"
    assert store.get("ghost").state == "failed"


def test_run_worker_once_drains_one():
    store = InMemoryRunStore()
    store.set("a", _queued("a"))
    log = InMemoryLogClient()
    rid = run_worker(run_store=store, registry=FakeRegistry([_SPEC]),
                     ctx_factory=lambda: _ctx(log), once=True)
    assert rid == "a"
    assert store.get("a").state == "done"


# ---- per-tool scope enforcement fires only when a principal is present -------

def test_tool_enforces_scope_for_authenticated_principal():
    from cleanroom.control.server import mcp as mcpmod
    from cleanroom.control.server.auth import AuthError

    reader = Principal(subject="u", tenant=None,
                       scopes=frozenset({"control:read"}), db_role=ROLE_READONLY)
    tok = current_principal.set(reader)
    try:
        # dispatch_run needs control:dispatch -> rejected before touching any backend
        with pytest.raises(AuthError):
            mcpmod.tool_dispatch_run("t1", "m", 1)
    finally:
        current_principal.reset(tok)
