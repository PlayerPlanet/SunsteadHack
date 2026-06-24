"""Task specification dataclass."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """A task specification for the optimization loop.

    Fields:
        task_id: Unique identifier for this task.
        objective: Human-readable description of the optimization goal.
        workload_id: Identifier for the workload to optimize (e.g., 'tpch_q5').
        action_space: List of allowed action types (subset of ['index', 'guc', 'rewrite']).
        db_ref: Reference to the database or connection string.
        constraints: Dict of constraints (e.g., {'memory_limit_gb': 16, 'time_limit_sec': 300}).
        default_model: Default model name for proposer inference (e.g., 'claude-3.5-sonnet').
    """

    task_id: str
    objective: str
    workload_id: str
    action_space: list[str]
    db_ref: str
    constraints: dict
    default_model: str
