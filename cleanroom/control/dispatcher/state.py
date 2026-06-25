"""Run status dataclass — snapshots a run's state and progress."""

from dataclasses import dataclass


@dataclass(slots=True)
class RunStatus:
    """Current status of an optimization run.

    Fields:
        run_id: Unique identifier for this run (UUID hex).
        task_id: Task being optimized.
        model: Model name used for proposer inference.
        state: One of 'queued', 'running', 'done', 'failed', 'cancelled'.
        iterations_done: Number of completed iterations.
        best_p99: Best (minimum) p99 latency seen so far, or None.
        started_at: ISO timestamp when run transitioned to 'running', or None.
        ended_at: ISO timestamp when run finished, or None.
        error_msg: Error message if state is 'failed', or None.
        iterations_target: Iterations requested at dispatch. Carries the dispatch
            parameter through the queue so a separate worker process (the
            deployment-grade web/worker split) knows how long to run. Defaults to 0
            for back-compat with callers that construct RunStatus directly.
    """

    run_id: str
    task_id: str
    model: str
    state: str
    iterations_done: int
    best_p99: float | None
    started_at: str | None
    ended_at: str | None
    error_msg: str | None
    iterations_target: int = 0
