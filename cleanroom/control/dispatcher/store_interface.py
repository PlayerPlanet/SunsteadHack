"""Swappable run store interface and in-memory implementation."""

import threading
from typing import Protocol

from cleanroom.control.dispatcher.state import RunStatus


class SwappableRunStore(Protocol):
    """Protocol for run state storage.

    Allows different backends (in-memory, Aiven knowledge base, etc.) to be plugged in.
    All methods must be thread-safe.
    """

    def get(self, run_id: str) -> RunStatus | None:
        """Retrieve a run by ID.

        Args:
            run_id: Run identifier.

        Returns:
            RunStatus if found, None otherwise.
        """
        ...

    def set(self, run_id: str, status: RunStatus) -> None:
        """Store or overwrite a run.

        Args:
            run_id: Run identifier.
            status: RunStatus object to store.
        """
        ...

    def list(self, filter: dict | None = None) -> list[RunStatus]:
        """List runs, optionally filtered by field=value.

        Args:
            filter: Optional dict of field=value constraints.

        Returns:
            List of matching RunStatus objects.
        """
        ...

    def update(self, run_id: str, **fields) -> RunStatus | None:
        """Update specific fields of a run.

        Args:
            run_id: Run identifier.
            **fields: Fields to update (e.g., state='done', iterations_done=5).

        Returns:
            Updated RunStatus, or None if not found.
        """
        ...

    def claim_next(self) -> RunStatus | None:
        """Atomically claim the oldest 'queued' run, transition it to 'running'.

        Returns the claimed RunStatus, or None if nothing is queued. Used by the
        worker process in the web/worker split so two workers never run the same job.
        """
        ...


class InMemoryRunStore:
    """In-memory thread-safe run store.

    Suitable for Phase-0 development and testing.
    """

    def __init__(self):
        """Initialize empty run storage."""
        self._runs: dict[str, RunStatus] = {}
        self._lock = threading.RLock()

    def get(self, run_id: str) -> RunStatus | None:
        """Retrieve a run by ID.

        Args:
            run_id: Run identifier.

        Returns:
            RunStatus if found, None otherwise.
        """
        with self._lock:
            return self._runs.get(run_id)

    def set(self, run_id: str, status: RunStatus) -> None:
        """Store or overwrite a run.

        Args:
            run_id: Run identifier.
            status: RunStatus object to store.
        """
        with self._lock:
            self._runs[run_id] = status

    def list(self, filter: dict | None = None) -> list[RunStatus]:
        """List runs, optionally filtered by field=value.

        Args:
            filter: Optional dict of field=value constraints.

        Returns:
            List of matching RunStatus objects.
        """
        with self._lock:
            if not filter:
                return list(self._runs.values())

            results = []
            for status in self._runs.values():
                match = True
                for key, value in filter.items():
                    if getattr(status, key, None) != value:
                        match = False
                        break
                if match:
                    results.append(status)
            return results

    def update(self, run_id: str, **fields) -> RunStatus | None:
        """Update specific fields of a run.

        Args:
            run_id: Run identifier.
            **fields: Fields to update (e.g., state='done', iterations_done=5).

        Returns:
            Updated RunStatus, or None if not found.
        """
        with self._lock:
            status = self._runs.get(run_id)
            if status is None:
                return None

            # Create updated status by copying and replacing fields
            data = {
                "run_id": status.run_id,
                "task_id": status.task_id,
                "model": status.model,
                "state": status.state,
                "iterations_done": status.iterations_done,
                "best_p99": status.best_p99,
                "started_at": status.started_at,
                "ended_at": status.ended_at,
                "error_msg": status.error_msg,
                "iterations_target": status.iterations_target,
            }
            data.update(fields)
            updated = RunStatus(**data)
            self._runs[run_id] = updated
            return updated

    def claim_next(self) -> RunStatus | None:
        """Atomically claim the oldest queued run and mark it 'running'.

        The lock makes claim-and-transition atomic, so concurrent workers never
        claim the same run. Insertion order (dict order) is the queue order.
        """
        with self._lock:
            for run_id, status in self._runs.items():
                if status.state == "queued":
                    claimed = RunStatus(
                        run_id=status.run_id,
                        task_id=status.task_id,
                        model=status.model,
                        state="running",
                        iterations_done=status.iterations_done,
                        best_p99=status.best_p99,
                        started_at=status.started_at,
                        ended_at=status.ended_at,
                        error_msg=status.error_msg,
                        iterations_target=status.iterations_target,
                    )
                    self._runs[run_id] = claimed
                    return claimed
            return None
