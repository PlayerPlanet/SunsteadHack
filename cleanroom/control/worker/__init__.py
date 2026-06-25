"""Dispatch worker for the deployment-grade web/worker split.

In a remote deployment the web tier (the streamable-HTTP MCP server) is stateless and
load-balanced, so it must NOT run optimization loops in a request thread. Instead
`dispatch_run(mode="queue")` leaves a run in state 'queued' in the shared run store
(Aiven Postgres), and one or more of these worker processes claim queued runs
atomically (PgRunStore.claim_next -> FOR UPDATE SKIP LOCKED) and execute them.

Run it as a process:  python -m cleanroom.control.worker

The worker reuses the same `_run_loop_worker` the in-process dispatcher uses, so the
governance log, progress tap, and cancellation semantics are identical — only *where*
the loop runs changes.
"""

import datetime
import threading
import time

from cleanroom.control.dispatcher.executor import _run_loop_worker


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _task_spec_to_dict(task_spec) -> dict:
    return {
        "task_id": task_spec.task_id,
        "objective": task_spec.objective,
        "workload_id": task_spec.workload_id,
        "action_space": task_spec.action_space,
        "db_ref": task_spec.db_ref,
        "constraints": task_spec.constraints,
        "default_model": task_spec.default_model,
    }


def run_once(*, run_store, registry, ctx_factory) -> str | None:
    """Claim one queued run and execute it to a terminal state.

    Returns the run_id processed, or None if the queue was empty. A fresh
    OperatorContext is built per run via `ctx_factory` (the worker is a separate
    process from the web tier, so it owns its own proposer/benchmark/logclient).
    """
    claimed = run_store.claim_next()
    if claimed is None:
        return None

    run_id = claimed.run_id
    task_spec = registry.get(claimed.task_id)
    if task_spec is None:
        run_store.update(
            run_id, state="failed",
            error_msg=f"Task {claimed.task_id} not found", ended_at=_now_iso(),
        )
        return run_id

    ctx = ctx_factory()
    cancel_event = threading.Event()
    # _run_loop_worker re-stamps state='running'+started_at, then runs the loop and
    # transitions to done/failed/cancelled. Synchronous: the worker IS the executor.
    _run_loop_worker(
        _task_spec_to_dict(task_spec),
        run_id,
        claimed.model,
        claimed.iterations_target,
        ctx,
        run_store,
        cancel_event,
    )
    return run_id


def run_worker(*, run_store, registry, ctx_factory, poll_interval: float = 1.0,
               once: bool = False, stop: threading.Event | None = None) -> str | None:
    """Poll the run store for queued runs and execute them.

    Drains back-to-back while work exists; sleeps `poll_interval` when the queue is
    empty. `once=True` processes a single run (or returns None) — used in tests.
    `stop` is an optional Event for graceful shutdown.
    """
    while True:
        run_id = run_once(run_store=run_store, registry=registry, ctx_factory=ctx_factory)
        if once:
            return run_id
        if stop is not None and stop.is_set():
            return run_id
        if run_id is None:
            time.sleep(poll_interval)
