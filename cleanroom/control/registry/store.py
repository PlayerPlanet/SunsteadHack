"""JSON-backed task registry with pending_judgment state tracking."""

import json
import os
from pathlib import Path

from cleanroom.control.registry.types import TaskSpec


class TaskRegistryStore:
    """JSON-backed persistent task registry.

    Tasks are stored as individual JSON files at cleanroom/control/tasks/<task_id>.json.
    A task can be in one of two states:
      - 'active': appears in list_tasks() and is eligible for dispatch.
      - 'pending_judgment': held on disk but not yet activated (awaiting human decision).
    """

    def __init__(self, tasks_dir: str | Path = "cleanroom/control/tasks"):
        """Initialize the registry with a tasks directory.

        Args:
            tasks_dir: Path to directory for storing task JSON files.
        """
        self.tasks_dir = Path(tasks_dir)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._active_tasks: dict[str, TaskSpec] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all active tasks from disk into memory."""
        self._active_tasks.clear()
        for file in self.tasks_dir.glob("*.json"):
            try:
                with open(file) as f:
                    data = json.load(f)
                    # Only load tasks that have 'state' not set to 'pending_judgment'
                    # or if 'state' is absent (backward compat), they are active.
                    if data.get("state") != "pending_judgment":
                        state = data.pop("state", "active")
                        # Keep task_id in data for TaskSpec constructor
                        spec = TaskSpec(**data)
                        self._active_tasks[spec.task_id] = spec
            except (json.JSONDecodeError, ValueError, KeyError):
                # Skip malformed files
                pass

    def list_tasks(self) -> list[TaskSpec]:
        """Return all active task specs.

        Does not include tasks in 'pending_judgment' state.

        Returns:
            List of TaskSpec objects.
        """
        return list(self._active_tasks.values())

    def get(self, task_id: str) -> TaskSpec | None:
        """Retrieve an active task spec by ID.

        Args:
            task_id: Task identifier.

        Returns:
            TaskSpec if active, None otherwise.
        """
        return self._active_tasks.get(task_id)

    def save(self, spec: TaskSpec, state: str = "active") -> None:
        """Save or update a task spec to disk.

        Args:
            spec: TaskSpec to save.
            state: State flag ('active' or 'pending_judgment').
        """
        task_file = self.tasks_dir / f"{spec.task_id}.json"
        data = {
            "task_id": spec.task_id,
            "objective": spec.objective,
            "workload_id": spec.workload_id,
            "action_space": spec.action_space,
            "db_ref": spec.db_ref,
            "constraints": spec.constraints,
            "default_model": spec.default_model,
            "state": state,
        }
        with open(task_file, "w") as f:
            json.dump(data, f, indent=2)

        # Reload active tasks if this is active, to make it immediately available
        if state == "active":
            self._load_all()

    def activate(self, task_id: str) -> None:
        """Promote a pending_judgment task to active.

        Reads the file, removes 'pending_judgment' state, and reloads.

        Args:
            task_id: Task identifier.
        """
        task_file = self.tasks_dir / f"{task_id}.json"
        if not task_file.exists():
            return

        with open(task_file) as f:
            data = json.load(f)

        # Remove pending_judgment marker
        data["state"] = "active"

        with open(task_file, "w") as f:
            json.dump(data, f, indent=2)

        # Reload from disk
        self._load_all()
