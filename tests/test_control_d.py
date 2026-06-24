"""Story D Phase-0 — control plane tests.

Covers:
  1. register_task allow path (NoOpPore → active immediately)
  2. register_task governance path (GovernancePore → pending, crossing written)
  3. pending_escalations filters correctly
  4. adjudicate approve → task activated, judgment row written
  5. adjudicate reject → task stays inactive
  6. dispatch_run fire-and-return, polls to done
  7. dispatch_run unknown task → run failed with error_msg
  8. read_curve returns experiments for the task
  9. list_runs filter by state
 10. cancel_run queued → deterministic cancelled
 11. RunScopedLogClient cancellation unit-test
"""

import threading
import time

import pytest

from cleanroom.control.dispatcher.executor import CancelledRun, RunScopedLogClient
from cleanroom.control.dispatcher.store_interface import InMemoryRunStore
from cleanroom.control.ops import Operator, OperatorContext
from cleanroom.control.registry.store import TaskRegistryStore
from cleanroom.control.registry.types import TaskSpec
from cleanroom.fixtures import (
    CannedBenchmark,
    DummyProposer,
    InMemoryLogClient,
    NoOpPore,
)
from cleanroom.types import PoreResult


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


class GovernancePore:
    """Pore that always escalates — used to trigger the governance hold path."""

    def evaluate(self, candidate):
        return PoreResult(
            pore="gov",
            risk_level="high",
            requires_human_judgment=True,
            decision="escalate",
        )


def _make_spec(task_id: str = "task-alpha") -> TaskSpec:
    return TaskSpec(
        task_id=task_id,
        objective="minimise p99 on tpch_q5",
        workload_id="tpch_q5",
        action_space=["index"],
        db_ref="db://test",
        constraints={"memory_limit_gb": 8},
        default_model="stub",
    )


def _make_operator(tmp_path) -> tuple[Operator, InMemoryLogClient]:
    registry = TaskRegistryStore(tmp_path / "tasks")
    run_store = InMemoryRunStore()
    logclient = InMemoryLogClient()
    op = Operator(registry, run_store)
    return op, logclient


def _make_ctx(logclient) -> OperatorContext:
    return OperatorContext(
        proposer=DummyProposer(),
        benchmark=CannedBenchmark(baseline_p99=100.0),
        pore=NoOpPore(),
        logclient=logclient,
    )


def _poll_until_terminal(op: Operator, run_id: str, timeout: float = 5.0):
    """Poll get_run until state is terminal; return final RunStatus."""
    terminal = {"done", "failed", "cancelled"}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = op.get_run(run_id)
        if status is not None and status.state in terminal:
            return status
        time.sleep(0.05)
    return op.get_run(run_id)


# ---------------------------------------------------------------------------
# 1. register_task — allow path
# ---------------------------------------------------------------------------


class TestRegisterTaskAllowPath:
    """NoOpPore lets the task through immediately."""

    def test_task_appears_active_in_list_tasks(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-allow")

        returned_id = op.register_task(spec, pore=NoOpPore(), logclient=logclient)

        assert returned_id == "task-allow"
        active_ids = [t.task_id for t in op.list_tasks()]
        assert "task-allow" in active_ids

    def test_get_task_returns_spec(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-allow-get")

        op.register_task(spec, pore=NoOpPore(), logclient=logclient)

        retrieved = op.get_task("task-allow-get")
        assert retrieved is not None
        assert retrieved.task_id == "task-allow-get"
        assert retrieved.objective == spec.objective


# ---------------------------------------------------------------------------
# 2. register_task — define/governance path (THE THESIS TEST)
# ---------------------------------------------------------------------------


class TestRegisterTaskGovernancePath:
    """GovernancePore escalates the registration — task must NOT become active.

    This is the 'can't move the goalposts' guarantee: registering a new task
    is itself a governed action.  A high-risk pore blocks it until a human
    explicitly approves the crossing.
    """

    def test_task_not_in_list_tasks_while_pending(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-gov")

        returned_id = op.register_task(spec, pore=GovernancePore(), logclient=logclient)

        assert returned_id == "task-gov"
        active_ids = [t.task_id for t in op.list_tasks()]
        # THE THESIS ASSERTION — task must NOT appear as active
        assert "task-gov" not in active_ids, (
            "Task appeared active despite being held pending_judgment — "
            "the governance guarantee is broken."
        )

    def test_exactly_one_crossing_with_requires_human_judgment(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-gov-crossing")

        op.register_task(spec, pore=GovernancePore(), logclient=logclient)

        human_crossings = [
            c for c in logclient.crossings if c.get("requires_human_judgment") is True
        ]
        assert len(human_crossings) == 1, (
            f"Expected exactly 1 human-judgment crossing, got {len(human_crossings)}"
        )
        # The crossing should reference the register_task action
        action = human_crossings[0].get("action", {})
        assert "register_task" in action, (
            "Crossing action does not carry the register_task payload"
        )


# ---------------------------------------------------------------------------
# 3. pending_escalations
# ---------------------------------------------------------------------------


class TestPendingEscalations:
    """pending_escalations returns only human-judgment crossings."""

    def test_returns_crossing_from_governance_registration(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-esc")

        op.register_task(spec, pore=GovernancePore(), logclient=logclient)

        escalations = op.pending_escalations(logclient)
        assert len(escalations) >= 1
        for e in escalations:
            assert e.get("requires_human_judgment") is True

    def test_filters_out_non_human_judgment_crossings(self, tmp_path):
        op, logclient = _make_operator(tmp_path)

        # Inject a crossing that does NOT require human judgment
        logclient.write_crossing(
            experiment_id=0,
            pore="noop",
            risk_level="low",
            requires_human_judgment=False,
            action={"some_action": {}},
        )

        # Now add a governance crossing
        spec = _make_spec("task-esc-filter")
        op.register_task(spec, pore=GovernancePore(), logclient=logclient)

        escalations = op.pending_escalations(logclient)
        # Only the governance crossing should be in escalations
        for e in escalations:
            assert e.get("requires_human_judgment") is True


# ---------------------------------------------------------------------------
# 4. adjudicate — approve activates the task
# ---------------------------------------------------------------------------


class TestAdjudicateApprove:
    """After a human approves, the held task becomes active."""

    def test_approve_activates_task(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-adj-approve")

        op.register_task(spec, pore=GovernancePore(), logclient=logclient)

        # Confirm still pending before adjudication
        assert "task-adj-approve" not in [t.task_id for t in op.list_tasks()]

        # Find the crossing id
        escalations = op.pending_escalations(logclient)
        assert len(escalations) == 1
        crossing_id = escalations[0]["id"]

        op.adjudicate(
            crossing_id,
            "approve",
            rationale="looks good to me",
            judge="alice",
            logclient=logclient,
        )

        # Task must now appear in list_tasks
        active_ids = [t.task_id for t in op.list_tasks()]
        assert "task-adj-approve" in active_ids

    def test_judgment_row_written_with_correct_metadata(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-adj-meta")

        op.register_task(spec, pore=GovernancePore(), logclient=logclient)
        escalations = op.pending_escalations(logclient)
        crossing_id = escalations[0]["id"]

        op.adjudicate(
            crossing_id,
            "approve",
            rationale="approved by test",
            judge="alice",
            logclient=logclient,
        )

        assert len(logclient.judgments) == 1
        j = logclient.judgments[0]
        assert j["judge_kind"] == "human"
        assert j["judge"] == "alice"
        assert j["decision"] == "approve"
        assert j["rationale"] == "approved by test"
        assert j["crossing_id"] == crossing_id


# ---------------------------------------------------------------------------
# 5. adjudicate — reject does NOT activate
# ---------------------------------------------------------------------------


class TestAdjudicateReject:
    """After a human rejects, the held task must remain inactive."""

    def test_reject_leaves_task_inactive(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-adj-reject")

        op.register_task(spec, pore=GovernancePore(), logclient=logclient)
        escalations = op.pending_escalations(logclient)
        crossing_id = escalations[0]["id"]

        op.adjudicate(
            crossing_id,
            "reject",
            rationale="not safe",
            judge="bob",
            logclient=logclient,
        )

        active_ids = [t.task_id for t in op.list_tasks()]
        assert "task-adj-reject" not in active_ids

    def test_reject_still_writes_judgment_row(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-adj-reject-j")

        op.register_task(spec, pore=GovernancePore(), logclient=logclient)
        escalations = op.pending_escalations(logclient)
        crossing_id = escalations[0]["id"]

        op.adjudicate(crossing_id, "reject", judge="bob", logclient=logclient)

        assert len(logclient.judgments) == 1
        assert logclient.judgments[0]["decision"] == "reject"


# ---------------------------------------------------------------------------
# 6. dispatch_run — fire-and-return + poll to done
# ---------------------------------------------------------------------------


class TestDispatchRunFireAndReturn:
    """dispatch_run returns immediately and eventually reaches 'done'."""

    def test_returns_run_id_string_quickly(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-dispatch")
        op.register_task(spec, pore=NoOpPore(), logclient=logclient)
        ctx = _make_ctx(logclient)

        t0 = time.monotonic()
        run_id = op.dispatch_run("task-dispatch", model="stub", iterations=4, ctx=ctx)
        elapsed = time.monotonic() - t0

        assert isinstance(run_id, str)
        assert len(run_id) > 0
        # Should return well before the loop could finish (< 2 s is very generous)
        assert elapsed < 2.0

    def test_run_transitions_to_done_with_progress(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-dispatch-done")
        op.register_task(spec, pore=NoOpPore(), logclient=logclient)
        ctx = _make_ctx(logclient)

        run_id = op.dispatch_run("task-dispatch-done", model="stub", iterations=4, ctx=ctx)

        # The run_id must be visible in the store immediately after dispatch returns
        initial_status = op.get_run(run_id)
        assert initial_status is not None, "run_id not in store immediately after dispatch"
        # State is queued, running, or already done (background thread is very fast
        # with the canned fixtures — all three are legitimate fire-and-return outcomes)
        assert initial_status.state in {"queued", "running", "done"}

        final = _poll_until_terminal(op, run_id, timeout=10.0)
        assert final is not None, "get_run returned None after polling"
        assert final.state == "done", f"Expected 'done', got {final.state!r}: {final.error_msg}"
        assert final.iterations_done > 0
        assert final.best_p99 is not None


# ---------------------------------------------------------------------------
# 7. dispatch_run — unknown task_id → failed run
# ---------------------------------------------------------------------------


class TestDispatchRunUnknownTask:
    """Dispatching against a non-existent task produces a 'failed' run."""

    def test_unknown_task_run_fails_with_error_msg(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        ctx = _make_ctx(logclient)

        run_id = op.dispatch_run("no-such-task", model="stub", iterations=2, ctx=ctx)

        final = _poll_until_terminal(op, run_id, timeout=5.0)
        assert final is not None
        assert final.state == "failed"
        assert final.error_msg is not None
        assert len(final.error_msg) > 0


# ---------------------------------------------------------------------------
# 8. read_curve
# ---------------------------------------------------------------------------


class TestReadCurve:
    """read_curve returns all experiments written for the task."""

    def test_read_curve_matches_iterations(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-curve")
        op.register_task(spec, pore=NoOpPore(), logclient=logclient)
        ctx = _make_ctx(logclient)

        iterations = 4
        run_id = op.dispatch_run("task-curve", model="stub", iterations=iterations, ctx=ctx)
        final = _poll_until_terminal(op, run_id, timeout=10.0)
        assert final is not None and final.state == "done"

        curve = op.read_curve("task-curve", logclient=logclient)
        # The loop writes one experiment per iteration (excluding baseline-only step);
        # at minimum it should be > 0 and match the iteration count written.
        assert len(curve) > 0
        assert len(curve) == final.iterations_done
        for exp in curve:
            assert exp["task_id"] == "task-curve"


# ---------------------------------------------------------------------------
# 9. list_runs filter
# ---------------------------------------------------------------------------


class TestListRunsFilter:
    """list_runs({'state': 'done'}) returns only done runs."""

    def test_filter_by_state_done(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-filter")
        op.register_task(spec, pore=NoOpPore(), logclient=logclient)
        ctx = _make_ctx(logclient)

        run_id = op.dispatch_run("task-filter", model="stub", iterations=3, ctx=ctx)
        final = _poll_until_terminal(op, run_id, timeout=10.0)
        assert final is not None and final.state == "done"

        done_runs = op.list_runs({"state": "done"})
        run_ids = [r.run_id for r in done_runs]
        assert run_id in run_ids

        for r in done_runs:
            assert r.state == "done"

    def test_filter_excludes_other_states(self, tmp_path):
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-filter2")
        op.register_task(spec, pore=NoOpPore(), logclient=logclient)
        ctx = _make_ctx(logclient)

        run_id = op.dispatch_run("task-filter2", model="stub", iterations=3, ctx=ctx)
        _poll_until_terminal(op, run_id, timeout=10.0)

        # Inject a 'failed' run manually via the run_store to create variety
        op.run_store.update(run_id, state="failed", error_msg="forced")

        done_runs = op.list_runs({"state": "done"})
        for r in done_runs:
            assert r.run_id != run_id


# ---------------------------------------------------------------------------
# 10. cancel_run — queued branch (deterministic)
# ---------------------------------------------------------------------------


class TestCancelRunQueued:
    """cancel_run on a queued run transitions it to 'cancelled' synchronously.

    We exploit the fact that dispatch_run for an unknown task marks the run
    failed before a thread is launched.  For queued cancellation we do a
    controlled test: we set up a run in queued state via the store directly
    and call cancel_run, verifying the synchronous fast-path.
    """

    def test_cancel_queued_run_transitions_to_cancelled(self, tmp_path):
        from cleanroom.control.dispatcher.state import RunStatus

        run_store = InMemoryRunStore()
        registry = TaskRegistryStore(tmp_path / "tasks")
        op = Operator(registry, run_store)

        # Manually insert a run in 'queued' state
        run_id = "test-cancel-001"
        run_store.set(
            run_id,
            RunStatus(
                run_id=run_id,
                task_id="task-x",
                model="stub",
                state="queued",
                iterations_done=0,
                best_p99=None,
                started_at=None,
                ended_at=None,
                error_msg=None,
            ),
        )

        op.cancel_run(run_id)

        status = op.get_run(run_id)
        assert status is not None
        assert status.state == "cancelled"
        assert status.ended_at is not None

    def test_cancel_dispatched_run_reaches_terminal(self, tmp_path):
        """Cancel a real dispatched run; final state must be in {'cancelled', 'done'}.

        Due to the thread/timing race (run may finish before cancel is registered),
        we accept both outcomes.  The invariant is: no exception, state is terminal.
        """
        op, logclient = _make_operator(tmp_path)
        spec = _make_spec("task-cancel-race")
        op.register_task(spec, pore=NoOpPore(), logclient=logclient)
        ctx = _make_ctx(logclient)

        run_id = op.dispatch_run("task-cancel-race", model="stub", iterations=20, ctx=ctx)
        # Cancel quickly — may still be queued or just transitioning to running
        op.cancel_run(run_id)

        final = _poll_until_terminal(op, run_id, timeout=10.0)
        assert final is not None
        assert final.state in {"cancelled", "done"}, (
            f"Unexpected terminal state: {final.state!r}"
        )


# ---------------------------------------------------------------------------
# 11. RunScopedLogClient — unit-test the tap directly
# ---------------------------------------------------------------------------


class TestRunScopedLogClientUnit:
    """Unit tests for the cancellation tap and iteration counter."""

    def _base_write_kwargs(self, task_id="task-unit"):
        return dict(
            task_id=task_id,
            model="stub",
            drift_level=0.0,
            candidate={"type": "index", "params": {}},
            baseline_p99=100.0,
            candidate_p99=90.0,
            cost_estimate=1.0,
            correctness_ok=True,
            within_noise=False,
            decision="keep",
        )

    def test_raises_cancelled_run_when_event_is_set(self, tmp_path):
        run_store = InMemoryRunStore()
        from cleanroom.control.dispatcher.state import RunStatus

        run_id = "unit-cancel"
        run_store.set(
            run_id,
            RunStatus(
                run_id=run_id,
                task_id="task-unit",
                model="stub",
                state="running",
                iterations_done=0,
                best_p99=None,
                started_at=None,
                ended_at=None,
                error_msg=None,
            ),
        )

        cancel_event = threading.Event()
        cancel_event.set()  # pre-cancelled

        wrapped = InMemoryLogClient()
        tap = RunScopedLogClient(wrapped, run_id, run_store, cancel_event)

        with pytest.raises(CancelledRun):
            tap.write_experiment(**self._base_write_kwargs())

        # The wrapped logclient must NOT have received the call
        assert len(wrapped.experiments) == 0

    def test_forwards_and_increments_iterations_when_not_cancelled(self, tmp_path):
        from cleanroom.control.dispatcher.state import RunStatus

        run_store = InMemoryRunStore()
        run_id = "unit-ok"
        run_store.set(
            run_id,
            RunStatus(
                run_id=run_id,
                task_id="task-unit",
                model="stub",
                state="running",
                iterations_done=0,
                best_p99=None,
                started_at=None,
                ended_at=None,
                error_msg=None,
            ),
        )

        cancel_event = threading.Event()  # not set
        wrapped = InMemoryLogClient()
        tap = RunScopedLogClient(wrapped, run_id, run_store, cancel_event)

        tap.write_experiment(**self._base_write_kwargs())

        # Forwarded to wrapped
        assert len(wrapped.experiments) == 1

        # Iteration counter incremented in store
        status = run_store.get(run_id)
        assert status.iterations_done == 1

    def test_updates_best_p99_on_improvement(self):
        from cleanroom.control.dispatcher.state import RunStatus

        run_store = InMemoryRunStore()
        run_id = "unit-p99"
        run_store.set(
            run_id,
            RunStatus(
                run_id=run_id,
                task_id="task-unit",
                model="stub",
                state="running",
                iterations_done=0,
                best_p99=None,
                started_at=None,
                ended_at=None,
                error_msg=None,
            ),
        )

        cancel_event = threading.Event()
        wrapped = InMemoryLogClient()
        tap = RunScopedLogClient(wrapped, run_id, run_store, cancel_event)

        # First call: best_p99 should be set to 80.0
        kwargs = self._base_write_kwargs()
        kwargs["candidate_p99"] = 80.0
        tap.write_experiment(**kwargs)
        assert run_store.get(run_id).best_p99 == 80.0

        # Second call with worse p99: best_p99 must NOT change
        kwargs["candidate_p99"] = 95.0
        tap.write_experiment(**kwargs)
        assert run_store.get(run_id).best_p99 == 80.0

        # Third call with better p99: best_p99 must improve
        kwargs["candidate_p99"] = 60.0
        tap.write_experiment(**kwargs)
        assert run_store.get(run_id).best_p99 == 60.0
