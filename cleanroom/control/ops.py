"""Core operator logic — task registration, dispatch, and run management.

This module implements the Operator class, which is the primary interface
for the control plane. It coordinates:
  1. Task registration (with governance via pore evaluation)
  2. Fire-and-return run dispatch (background daemon threads)
  3. Real-time progress tracking (via RunScopedLogClient tap)
  4. Run cancellation (via threading.Event)
  5. Escalation queries
  6. Human adjudication
  7. Performance curve aggregation

All public methods are thread-safe via the SwappableRunStore's internal locking.
"""

import datetime
import threading
import uuid

from cleanroom.control.dispatcher.executor import dispatch_background_run
from cleanroom.control.dispatcher.state import RunStatus
from cleanroom.control.dispatcher.store_interface import SwappableRunStore
from cleanroom.control.pore_boundary.escalation import pending_escalations
from cleanroom.control.registry.store import TaskRegistryStore
from cleanroom.control.registry.types import TaskSpec
from cleanroom.types import Candidate


class OperatorContext:
    """Injected context for a single dispatch — provides loop dependencies.

    The dispatcher receives this context and passes it to the background thread,
    which uses it to invoke run_loop(..., proposer=ctx.proposer, ...).
    """

    def __init__(self, *, proposer, benchmark, pore, logclient):
        """Initialize context with required components.

        Args:
            proposer: Object with propose(task_spec, history) -> Candidate method.
            benchmark: Object with run_benchmark, check_correctness, is_within_noise methods.
            pore: Object with evaluate(candidate) -> PoreResult method.
            logclient: LogClient protocol for write_experiment, write_crossing, etc.
        """
        self.proposer = proposer
        self.benchmark = benchmark
        self.pore = pore
        self.logclient = logclient


class Operator:
    """Control plane operator — task and run manager.

    Public interface:
      - list_tasks() -> list[TaskSpec]
      - get_task(task_id) -> TaskSpec | None
      - register_task(spec: TaskSpec, *, pore, logclient) -> str
      - dispatch_run(task_id, *, model, iterations, ctx: OperatorContext) -> str
      - get_run(run_id) -> RunStatus | None
      - list_runs(filter: dict | None) -> list[RunStatus]
      - cancel_run(run_id) -> None
      - pending_escalations(logclient) -> list[dict]
      - adjudicate(crossing_id, decision, rationale, *, judge, logclient) -> None
      - read_curve(task_id, *, logclient) -> list[dict]
    """

    def __init__(self, registry: TaskRegistryStore, run_store: SwappableRunStore):
        """Initialize the operator.

        Args:
            registry: TaskRegistryStore for task persistence.
            run_store: SwappableRunStore for run state (InMemoryRunStore recommended for Phase 0).
        """
        self.registry = registry
        self.run_store = run_store
        self._cancel_events: dict[str, threading.Event] = {}
        self._cancel_lock = threading.RLock()

    def list_tasks(self) -> list[TaskSpec]:
        """List all active tasks.

        Does not include tasks in pending_judgment state.

        Returns:
            List of TaskSpec objects.
        """
        return self.registry.list_tasks()

    def get_task(self, task_id: str) -> TaskSpec | None:
        """Retrieve a task specification by ID.

        Args:
            task_id: Task identifier.

        Returns:
            TaskSpec if found and active, None otherwise.
        """
        return self.registry.get(task_id)

    def register_task(
        self, spec: TaskSpec, *, pore, logclient
    ) -> str:
        """Register a new task (governance-gated).

        Flow:
          1. Build Candidate(type='task_definition', params=spec as dict)
          2. Call pore.evaluate(candidate)
          3. If decision is 'block' or 'escalate', or requires_human_judgment:
             - Write spec to disk as pending_judgment
             - Write crossing to logclient with action={'register_task': spec dict}
             - Return task_id (NOT activated yet)
          4. If allowed outright:
             - Write spec to disk as active
             - Return task_id (active immediately)

        Args:
            spec: TaskSpec to register.
            pore: Pore evaluator.
            logclient: LogClient for governance log.

        Returns:
            task_id (string). Task may be pending judgment or active.
        """
        # Build candidate for governance evaluation
        candidate = Candidate(
            type="task_definition",
            params={
                "task_id": spec.task_id,
                "objective": spec.objective,
                "workload_id": spec.workload_id,
                "action_space": spec.action_space,
                "db_ref": spec.db_ref,
                "constraints": spec.constraints,
                "default_model": spec.default_model,
            },
            reversible=False,
        )

        # Evaluate via pore
        pore_result = pore.evaluate(candidate)

        # Decide: escalate or block?
        if (
            pore_result.requires_human_judgment
            or pore_result.decision in ("escalate", "block")
        ):
            # Hold as pending_judgment
            self.registry.save(spec, state="pending_judgment")

            # Write crossing for human review
            logclient.write_crossing(
                experiment_id=0,  # No experiment yet
                pore=pore_result.pore,
                risk_level=pore_result.risk_level,
                requires_human_judgment=True,
                action={"register_task": candidate.params},
            )

            return spec.task_id

        # Allowed — activate immediately
        self.registry.save(spec, state="active")
        return spec.task_id

    def dispatch_run(
        self, task_id: str, *, model: str, iterations: int, ctx: OperatorContext
    ) -> str:
        """Dispatch a run (fire-and-return, background thread).

        Flow:
          1. Generate run_id = uuid.uuid4().hex[:12]
          2. Create RunStatus(state='queued')
          3. Store in run_store
          4. Launch daemon thread with dispatch_background_run
          5. Return run_id immediately (never join)

        The thread will:
          - Update RunStatus to 'running' (stamp started_at)
          - Call run_loop with a RunScopedLogClient tap
          - On success: state='done'
          - On CancelledRun: state='cancelled'
          - On any other exception: state='failed' + error_msg
          - Always stamp ended_at

        Args:
            task_id: Task ID to optimize.
            model: Model name for proposer inference.
            iterations: Number of optimization iterations.
            ctx: OperatorContext with proposer, benchmark, pore, logclient.

        Returns:
            run_id (string, 12-char hex). Caller can poll get_run(run_id) for status.
        """
        # Generate run_id
        run_id = uuid.uuid4().hex[:12]

        # Create and store initial RunStatus
        initial_status = RunStatus(
            run_id=run_id,
            task_id=task_id,
            model=model,
            state="queued",
            iterations_done=0,
            best_p99=None,
            started_at=None,
            ended_at=None,
            error_msg=None,
        )
        self.run_store.set(run_id, initial_status)

        # Create cancel event for this run
        cancel_event = threading.Event()
        with self._cancel_lock:
            self._cancel_events[run_id] = cancel_event

        # Get task spec
        task_spec = self.registry.get(task_id)
        if task_spec is None:
            # Task not found — mark run as failed
            now_iso = datetime.datetime.now(datetime.UTC).isoformat()
            self.run_store.update(
                run_id,
                state="failed",
                error_msg=f"Task {task_id} not found",
                ended_at=now_iso,
            )
            return run_id

        # Convert TaskSpec to dict for run_loop
        task_spec_dict = {
            "task_id": task_spec.task_id,
            "objective": task_spec.objective,
            "workload_id": task_spec.workload_id,
            "action_space": task_spec.action_space,
            "db_ref": task_spec.db_ref,
            "constraints": task_spec.constraints,
            "default_model": task_spec.default_model,
        }

        # Launch background thread (fire-and-return)
        dispatch_background_run(
            task_spec_dict,
            run_id,
            model,
            iterations,
            ctx,
            self.run_store,
            cancel_event,
        )

        return run_id

    def get_run(self, run_id: str) -> RunStatus | None:
        """Retrieve run status by ID (pollable).

        Args:
            run_id: Run identifier.

        Returns:
            RunStatus if found, None otherwise.
        """
        return self.run_store.get(run_id)

    def list_runs(self, filter: dict | None = None) -> list[RunStatus]:
        """List runs, optionally filtered.

        Args:
            filter: Optional dict of field=value constraints (e.g., {'state': 'running'}).

        Returns:
            List of matching RunStatus objects.
        """
        return self.run_store.list(filter=filter)

    def cancel_run(self, run_id: str) -> None:
        """Request cancellation of a run.

        If the run is 'queued', marks it 'cancelled' immediately.
        If the run is 'running', sets the cancel event; the next write_experiment
        tap will detect it and raise CancelledRun, transitioning to 'cancelled'.

        Args:
            run_id: Run identifier.
        """
        status = self.run_store.get(run_id)
        if status is None:
            # Unknown run
            return

        # If queued, mark as cancelled immediately
        if status.state == "queued":
            now_iso = datetime.datetime.now(datetime.UTC).isoformat()
            self.run_store.update(
                run_id, state="cancelled", ended_at=now_iso
            )
            return

        # If running, set the cancel event for the background thread to pick up
        with self._cancel_lock:
            cancel_event = self._cancel_events.get(run_id)

        if cancel_event is not None:
            cancel_event.set()

    def pending_escalations(self, logclient) -> list[dict]:
        """List all pending escalations (crossings requiring human judgment).

        Args:
            logclient: LogClient instance.

        Returns:
            List of crossing dicts with requires_human_judgment=True.
        """
        return pending_escalations(logclient)

    def adjudicate(
        self,
        crossing_id: int,
        decision: str,
        rationale: str | None = None,
        *,
        judge: str = "human",
        logclient,
    ) -> None:
        """Human decision on a crossing (approve/reject register_task or other action).

        Flow:
          1. Write judgment to logclient with decision, rationale, judge.
          2. If the crossing was a register_task action and decision is 'approve'/'allow':
             - Extract task_id from crossing's action dict
             - Call activate(task_id) to promote from pending_judgment to active

        Args:
            crossing_id: Crossing ID from escalations.
            decision: Human decision (e.g., 'approve', 'reject', 'allow', 'block').
            rationale: Optional explanation.
            judge: Judge identifier (default 'human').
            logclient: LogClient instance.
        """
        # Write judgment
        logclient.write_judgment(
            crossing_id=crossing_id,
            judge=judge,
            judge_kind="human",
            decision=decision,
            rationale=rationale,
        )

        # Check if this was a register_task escalation and decision is approve
        # For Phase 0, we'll scan the in-memory logclient.crossings directly
        # TODO(integration#4): Replace with logclient.read_crossings(filter={...})
        if hasattr(logclient, "crossings"):
            for crossing in logclient.crossings:
                if crossing.get("id") == crossing_id:
                    action = crossing.get("action", {})
                    if "register_task" in action and decision in (
                        "approve",
                        "allow",
                    ):
                        task_id = action["register_task"].get("task_id")
                        if task_id:
                            self.registry.activate(task_id)
                    break

    def read_curve(self, task_id: str, *, logclient) -> list[dict]:
        """Read performance curve (all experiments for a task).

        Args:
            task_id: Task identifier.
            logclient: LogClient instance.

        Returns:
            List of experiment dicts (as returned by logclient.read_experiments).
        """
        return logclient.read_experiments(filter={"task_id": task_id})
