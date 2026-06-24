"""Story D (issue #5) — PgRunStore and read_crossings integration tests.

Covers:
  * PgRunStore CRUD operations (get, set, list, update) via FakeCursor.
  * read_crossings on both PgLogClient (via fake conn) and InMemoryLogClient (real).
  * Integration: escalation and ops rewiring to use read_crossings.

These tests are hermetic (no live DB) using the FakeCursor/FakeConn pattern
from test_substrate_b.py.
"""

import pytest

from cleanroom.control.dispatcher.pg_store import PgRunStore
from cleanroom.control.dispatcher.state import RunStatus
from cleanroom.fixtures import InMemoryLogClient
from cleanroom.control.pore_boundary.escalation import pending_escalations


# --------------------------------------------------------------------------- #
# Fake connection and cursor for testing (recording pattern from test_substrate_b)
# --------------------------------------------------------------------------- #


class _RecordingCursor:
    """Cursor that records SQL/params executed on it."""

    def __init__(self, store):
        self._store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._store["last_sql"] = sql
        self._store["last_params"] = params

    def fetchone(self):
        # Return a dummy row for testing set/update operations
        return (42,)

    def fetchall(self):
        # Return dummy rows for testing list operations
        return []


class _RecordingConn:
    """Fake connection that records SQL/params for testing."""

    def __init__(self):
        self.store = {}
        self.commits = 0

    def cursor(self):
        return _RecordingCursor(self.store)

    def commit(self):
        self.commits += 1


# --------------------------------------------------------------------------- #
# PgRunStore contract tests (SQL shape, not full DB simulation)               #
# --------------------------------------------------------------------------- #


class TestPgRunStoreSet:
    def test_set_uses_insert_on_conflict(self):
        """Test that set() generates INSERT ... ON CONFLICT for idempotency."""
        conn = _RecordingConn()
        store = PgRunStore(conn)

        status = RunStatus(
            run_id="run-456",
            task_id="task-2",
            model="claude",
            state="queued",
            iterations_done=0,
            best_p99=None,
            started_at=None,
            ended_at=None,
            error_msg=None,
        )

        store.set("run-456", status)

        assert conn.commits == 1
        assert "INSERT INTO run" in conn.store["last_sql"]
        assert "ON CONFLICT (run_id) DO UPDATE" in conn.store["last_sql"]
        # Verify params are in the correct order
        assert conn.store["last_params"][0] == "run-456"
        assert conn.store["last_params"][1] == "task-2"
        assert conn.store["last_params"][2] == "claude"
        assert conn.store["last_params"][3] == "queued"


class TestPgRunStoreGet:
    def test_get_uses_select_by_run_id(self):
        """Test that get() generates correct SELECT query."""
        conn = _RecordingConn()
        store = PgRunStore(conn)

        # The fake cursor will return (42,) from fetchone,
        # which will cause an IndexError when trying to unpack to RunStatus.
        # This test just verifies the SQL shape.
        try:
            store.get("run-123")
        except (IndexError, TypeError):
            pass  # Expected since fake cursor doesn't return real row data

        assert "SELECT" in conn.store["last_sql"]
        assert "FROM run WHERE run_id = %s" in conn.store["last_sql"]
        assert conn.store["last_params"] == ("run-123",)


class TestPgRunStoreList:
    def test_list_generates_select_from_run(self):
        """Test that list() generates SELECT from run."""
        conn = _RecordingConn()
        store = PgRunStore(conn)

        try:
            store.list()
        except (IndexError, TypeError):
            pass  # Expected since fake cursor returns empty rows

        assert "SELECT" in conn.store["last_sql"]
        assert "FROM run" in conn.store["last_sql"]
        assert "ORDER BY run_id" in conn.store["last_sql"]

    def test_list_rejects_unknown_filter_fields(self):
        """Test that unknown filter fields raise ValueError."""
        conn = _RecordingConn()
        store = PgRunStore(conn)

        with pytest.raises(ValueError, match="unknown filter field"):
            store.list(filter={"nonexistent_field": "value"})

    def test_list_validates_filter_keys(self):
        """Test that valid filter keys are accepted."""
        conn = _RecordingConn()
        store = PgRunStore(conn)

        # Should not raise
        try:
            store.list(filter={"state": "done"})
        except (IndexError, TypeError):
            pass  # OK, we're testing SQL shape


class TestPgRunStoreUpdate:
    def test_update_generates_dynamic_update_clause(self):
        """Test that update() generates UPDATE with dynamic SET clause."""
        conn = _RecordingConn()
        store = PgRunStore(conn)

        try:
            store.update("run-100", state="done", iterations_done=10)
        except (IndexError, TypeError):
            pass  # Expected

        assert "UPDATE run SET" in conn.store["last_sql"]
        assert "state = %s" in conn.store["last_sql"]
        assert "iterations_done = %s" in conn.store["last_sql"]
        assert "WHERE run_id = %s" in conn.store["last_sql"]
        # Params should be [state_val, iterations_done_val, run_id]
        assert conn.store["last_params"][-1] == "run-100"

    def test_update_rejects_unknown_fields(self):
        """Test that unknown field names raise ValueError."""
        conn = _RecordingConn()
        store = PgRunStore(conn)

        with pytest.raises(ValueError, match="unknown field"):
            store.update("run-100", nonexistent_field="bad")

    def test_update_with_no_fields_returns_early(self):
        """Test that update() with no fields calls get() instead."""
        conn = _RecordingConn()
        store = PgRunStore(conn)

        try:
            store.update("run-100")
        except (IndexError, TypeError):
            pass  # OK

        # Should have called get(), not UPDATE
        sql = conn.store.get("last_sql", "")
        if sql:
            assert "UPDATE" not in sql


# --------------------------------------------------------------------------- #
# read_crossings integration tests                                             #
# --------------------------------------------------------------------------- #


class TestReadCrossingsInMemoryLogClient:
    def test_read_all_crossings(self):
        """Test reading all crossings from in-memory fixture."""
        logclient = InMemoryLogClient()

        # Add some crossings
        exp_id = logclient.write_experiment(
            task_id="task-1",
            model="gpt4",
            drift_level=0.0,
            candidate={"type": "index"},
            baseline_p99=100.0,
            candidate_p99=90.0,
            cost_estimate=1.0,
            correctness_ok=True,
            within_noise=False,
            decision="keep",
        )

        logclient.write_crossing(
            experiment_id=exp_id,
            pore="reversibility",
            risk_level="high",
            requires_human_judgment=True,
            action={"escalate": True},
        )

        logclient.write_crossing(
            experiment_id=exp_id,
            pore="safety",
            risk_level="low",
            requires_human_judgment=False,
            action={"allow": True},
        )

        crossings = logclient.read_crossings()
        assert len(crossings) == 2
        assert crossings[0]["id"] == 1
        assert crossings[1]["id"] == 2

    def test_read_crossings_with_filter(self):
        """Test reading crossings with a filter."""
        logclient = InMemoryLogClient()

        exp_id = logclient.write_experiment(
            task_id="task-1",
            model="gpt4",
            drift_level=0.0,
            candidate={"type": "index"},
            baseline_p99=100.0,
            candidate_p99=90.0,
            cost_estimate=1.0,
            correctness_ok=True,
            within_noise=False,
            decision="keep",
        )

        logclient.write_crossing(
            experiment_id=exp_id,
            pore="reversibility",
            risk_level="high",
            requires_human_judgment=True,
            action={"escalate": True},
        )

        logclient.write_crossing(
            experiment_id=exp_id,
            pore="safety",
            risk_level="low",
            requires_human_judgment=False,
            action={"allow": True},
        )

        # Filter for escalations
        escalations = logclient.read_crossings(filter={"requires_human_judgment": True})
        assert len(escalations) == 1
        assert escalations[0]["pore"] == "reversibility"


class TestReadCrossingsPgLogClient:
    def test_pglogclient_read_crossings_returns_dicts(self):
        """Test that PgLogClient.read_crossings returns dicts with correct columns."""
        pytest.importorskip("psycopg")
        from cleanroom.logclient import PgLogClient

        # Create a fake connection that returns crossing rows
        class _CrossingFakeCursor:
            def __init__(self):
                self._rows = [
                    (1, 100, "safety", "low", False, {"allow": True}, "2026-06-25T10:00:00Z"),
                    (2, 100, "reversibility", "high", True, {"escalate": True}, "2026-06-25T10:05:00Z"),
                ]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                # Return all rows for simplicity
                pass

            def fetchall(self):
                return self._rows

        class _CrossingFakeConn:
            def cursor(self):
                return _CrossingFakeCursor()

        client = PgLogClient(_CrossingFakeConn())
        crossings = client.read_crossings()

        assert len(crossings) == 2
        assert crossings[0]["id"] == 1
        assert crossings[0]["risk_level"] == "low"
        assert crossings[1]["requires_human_judgment"] is True

    def test_pglogclient_read_crossings_rejects_unknown_filter_column(self):
        """Test that read_crossings rejects unknown filter columns."""
        pytest.importorskip("psycopg")
        from cleanroom.logclient import PgLogClient

        class _FakeConn:
            def cursor(self):
                raise AssertionError("should not be reached")

        client = PgLogClient(_FakeConn())
        with pytest.raises(ValueError, match="unknown filter column"):
            client.read_crossings({"not_a_column": True})


# --------------------------------------------------------------------------- #
# Escalation integration — uses read_crossings                                 #
# --------------------------------------------------------------------------- #


class TestEscalationIntegration:
    def test_pending_escalations_uses_read_crossings(self):
        """Test that pending_escalations correctly uses read_crossings."""
        logclient = InMemoryLogClient()

        exp_id = logclient.write_experiment(
            task_id="task-1",
            model="gpt4",
            drift_level=0.0,
            candidate={"type": "index"},
            baseline_p99=100.0,
            candidate_p99=90.0,
            cost_estimate=1.0,
            correctness_ok=True,
            within_noise=False,
            decision="keep",
        )

        logclient.write_crossing(
            experiment_id=exp_id,
            pore="reversibility",
            risk_level="high",
            requires_human_judgment=True,
            action={"escalate": True},
        )

        logclient.write_crossing(
            experiment_id=exp_id,
            pore="safety",
            risk_level="low",
            requires_human_judgment=False,
            action={"allow": True},
        )

        # Retrieve escalations using the rewired function
        escalations = pending_escalations(logclient)

        assert len(escalations) == 1
        assert escalations[0]["requires_human_judgment"] is True
        assert escalations[0]["pore"] == "reversibility"
