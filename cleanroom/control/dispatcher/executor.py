"""Background executor and progress tap for run_loop invocations."""

import datetime
import logging
import os
import threading
from typing import Callable

from cleanroom import loop
from cleanroom.benchmark import register_workload
from cleanroom.benchmark.workloads import WORKLOAD_CATALOG
from cleanroom.control.dispatcher.state import RunStatus
from cleanroom.control.dispatcher.store_interface import SwappableRunStore

logger = logging.getLogger(__name__)


class CancelledRun(Exception):
    """Raised by RunScopedLogClient when a run has been cancelled."""

    pass


class RunScopedLogClient:
    """Wrapper around a logclient that taps progress and checks for cancellation.

    This is the key piece that enables real-time progress tracking and cancellation:
    - Forwards all method calls to the wrapped logclient (preserving the governance log).
    - On each write_experiment call: checks cancel flag, increments iterations_done,
      updates best_p99 from candidate_p99 if improved.
    - Thread-safe via the run_store's internal lock.
    """

    def __init__(
        self,
        wrapped_logclient,
        run_id: str,
        run_store: SwappableRunStore,
        cancel_event: threading.Event,
    ):
        """Initialize the progress-tapping logclient wrapper.

        Args:
            wrapped_logclient: The real logclient to forward calls to.
            run_id: The run ID to track progress for.
            run_store: The run store for atomic status updates.
            cancel_event: threading.Event that's set when run should cancel.
        """
        self.wrapped_logclient = wrapped_logclient
        self.run_id = run_id
        self.run_store = run_store
        self.cancel_event = cancel_event

    def write_experiment(
        self,
        task_id: str,
        model: str,
        drift_level: float,
        candidate: dict,
        baseline_p99: float | None,
        candidate_p99: float | None,
        cost_estimate: float | None,
        correctness_ok: bool | None,
        within_noise: bool | None,
        decision: str,
    ) -> int:
        """Tap: check cancel, increment iterations, update best_p99, then forward.

        Args:
            task_id: Task identifier.
            model: Model name.
            drift_level: Drift level.
            candidate: Candidate params dict.
            baseline_p99: Baseline p99 latency.
            candidate_p99: Candidate p99 latency.
            cost_estimate: Cost estimate.
            correctness_ok: Correctness check result.
            within_noise: Within noise flag.
            decision: Experiment decision.

        Returns:
            Experiment ID from the wrapped logclient.

        Raises:
            CancelledRun: If cancel_event is set.
        """
        # Check cancel flag
        if self.cancel_event.is_set():
            raise CancelledRun(f"Run {self.run_id} was cancelled")

        # Forward to wrapped logclient
        exp_id = self.wrapped_logclient.write_experiment(
            task_id=task_id,
            model=model,
            drift_level=drift_level,
            candidate=candidate,
            baseline_p99=baseline_p99,
            candidate_p99=candidate_p99,
            cost_estimate=cost_estimate,
            correctness_ok=correctness_ok,
            within_noise=within_noise,
            decision=decision,
        )

        # Tap: increment iterations_done
        self.run_store.update(self.run_id, iterations_done=self._get_current_iterations() + 1)

        # Tap: update best_p99 if we have a candidate result
        if candidate_p99 is not None:
            self._update_best_p99(candidate_p99)

        return exp_id

    def write_crossing(
        self,
        experiment_id: int,
        pore: str,
        risk_level: str,
        requires_human_judgment: bool,
        action: dict,
    ) -> int:
        """Forward to wrapped logclient (no tap needed here)."""
        return self.wrapped_logclient.write_crossing(
            experiment_id=experiment_id,
            pore=pore,
            risk_level=risk_level,
            requires_human_judgment=requires_human_judgment,
            action=action,
        )

    def write_judgment(
        self,
        crossing_id: int,
        judge: str,
        judge_kind: str,
        decision: str,
        rationale: str | None = None,
    ) -> None:
        """Forward to wrapped logclient."""
        return self.wrapped_logclient.write_judgment(
            crossing_id=crossing_id,
            judge=judge,
            judge_kind=judge_kind,
            decision=decision,
            rationale=rationale,
        )

    def read_experiments(self, filter: dict | None = None) -> list[dict]:
        """Forward to wrapped logclient."""
        return self.wrapped_logclient.read_experiments(filter=filter)

    def _get_current_iterations(self) -> int:
        """Helper to get current iterations_done from run_store."""
        status = self.run_store.get(self.run_id)
        return status.iterations_done if status else 0

    def _update_best_p99(self, candidate_p99: float) -> None:
        """Helper to update best_p99 if this is better than current."""
        status = self.run_store.get(self.run_id)
        if status is None:
            return

        current_best = status.best_p99
        if current_best is None or candidate_p99 < current_best:
            self.run_store.update(self.run_id, best_p99=candidate_p99)


def _run_loop_worker(
    task_spec: dict,
    run_id: str,
    model: str,
    iterations: int,
    ctx,
    run_store: SwappableRunStore,
    cancel_event: threading.Event,
) -> None:
    """Worker function for background thread execution.

    Runs the loop, updates RunStatus atomically, and handles all exceptions.

    Args:
        task_spec: Task specification dict.
        run_id: Run ID for this execution.
        model: Model name to use.
        iterations: Number of iterations to run.
        ctx: OperatorContext with proposer, benchmark, pore, logclient.
        run_store: SwappableRunStore for atomic status updates.
        cancel_event: threading.Event for cancellation signaling.
    """
    workload_conn = None
    try:
        # Mark as running
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        run_store.update(run_id, state="running", started_at=now_iso)

        # Wrap the logclient with progress tap
        tapped_logclient = RunScopedLogClient(
            ctx.logclient, run_id, run_store, cancel_event
        )

        # Inject model and task_id into task_spec for run_loop
        task_spec_copy = dict(task_spec)
        task_spec_copy["model"] = model
        task_spec_copy["task_id"] = task_spec_copy.get("task_id", "unknown")

        # Register workload from catalog if task specifies a workload_id
        workload_id = task_spec_copy.get("workload_id")
        if workload_id and workload_id != "__default__":
            if workload_id in WORKLOAD_CATALOG:
                register_workload(workload_id, WORKLOAD_CATALOG[workload_id])
            else:
                # Log a warning but don't crash; the benchmark will fall back to __default__
                # (unless the workload is already registered in the same process)
                logger.warning(
                    f"workload_id {workload_id!r} not in catalog and not pre-registered; "
                    f"falling back to '__default__'. Known workloads: {sorted(WORKLOAD_CATALOG)}"
                )

        # integration#1: a Postgres task carries no conn (domains seed an env dict via
        # bind_domain). Open the workload DB connection from CLEANROOM_WORKLOAD_DSN so
        # run_loop's benchmark + actions have a real psycopg connection; closed in the
        # finally below. Autocommit so reversible CREATE/DROP INDEX persist per step.
        if task_spec_copy.get("conn") is None:
            workload_dsn = os.environ.get("CLEANROOM_WORKLOAD_DSN")
            if workload_dsn:
                from cleanroom.db import connect

                workload_conn = connect(workload_dsn, autocommit=True)
                task_spec_copy["conn"] = workload_conn

        # Run the loop. ctx.actions is None for Postgres tasks (run_loop falls back
        # to the builtin cleanroom.actions) and the domain adapter for epic #8 tasks.
        loop.run_loop(
            task_spec_copy,
            proposer=ctx.proposer,
            benchmark=ctx.benchmark,
            pore=ctx.pore,
            logclient=tapped_logclient,
            actions=getattr(ctx, "actions", None),
            iterations=iterations,
        )

        # Mark as done
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        run_store.update(run_id, state="done", ended_at=now_iso)

    except CancelledRun:
        # Graceful cancellation
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        run_store.update(run_id, state="cancelled", ended_at=now_iso)

    except Exception as e:
        # Unexpected error
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        run_store.update(
            run_id,
            state="failed",
            error_msg=str(e),
            ended_at=now_iso,
        )

    finally:
        # Close the workload connection if integration#1 opened one for this run.
        if workload_conn is not None:
            try:
                workload_conn.close()
            except Exception:
                pass


def dispatch_background_run(
    task_spec: dict,
    run_id: str,
    model: str,
    iterations: int,
    ctx,
    run_store: SwappableRunStore,
    cancel_event: threading.Event,
) -> None:
    """Launch a daemon thread to run the loop.

    Args:
        task_spec: Task specification dict.
        run_id: Run ID for this execution.
        model: Model name to use.
        iterations: Number of iterations to run.
        ctx: OperatorContext with proposer, benchmark, pore, logclient.
        run_store: SwappableRunStore for atomic status updates.
        cancel_event: threading.Event for cancellation signaling.
    """
    thread = threading.Thread(
        target=_run_loop_worker,
        args=(task_spec, run_id, model, iterations, ctx, run_store, cancel_event),
        daemon=True,
    )
    thread.start()
