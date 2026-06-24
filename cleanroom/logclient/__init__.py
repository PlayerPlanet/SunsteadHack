"""Logging client protocol and implementations.

Story B (GitHub issue #3) owns the production LogClient. This module defines
the contract protocol so Stories A and C can type against it using fixtures.
"""

from typing import Protocol

from cleanroom.types import PoreResult


class LogClient(Protocol):
    """Protocol for writing and reading experiment/crossing/judgment records.

    Implementations must support both in-memory (for fixtures) and persistent
    (PostgreSQL, Story B) backends.
    """

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
        """Write an experiment record.

        Args:
            task_id: Identifier for the optimization task.
            model: Model name or version.
            drift_level: Detected drift from baseline.
            candidate: Candidate dict {type, params, reversible}.
            baseline_p99: Baseline p99 latency (ms).
            candidate_p99: Candidate p99 latency (ms).
            cost_estimate: Estimated cost.
            correctness_ok: Whether correctness checks passed.
            within_noise: Whether candidate is within noise threshold.
            decision: One of 'keep', 'discard', 'rollback', 'escalated'.

        Returns:
            The experiment ID (bigint primary key).
        """
        raise NotImplementedError("write_experiment — owned by Story B, GitHub issue #3")

    def write_crossing(
        self,
        experiment_id: int,
        pore: str,
        risk_level: str,
        requires_human_judgment: bool,
        action: dict,
    ) -> int:
        """Write a crossing (pore evaluation) record.

        Args:
            experiment_id: Reference to experiment(id).
            pore: Identifier for the pore rule.
            risk_level: One of 'low', 'medium', 'high'.
            requires_human_judgment: Whether human review is needed.
            action: Action dict describing the escalation or approval.

        Returns:
            The crossing ID (bigint primary key).
        """
        raise NotImplementedError("write_crossing — owned by Story B, GitHub issue #3")

    def write_judgment(
        self,
        crossing_id: int,
        judge: str,
        judge_kind: str,
        decision: str,
        rationale: str | None = None,
    ) -> None:
        """Write a judgment (human/rule/agent review) record.

        Args:
            crossing_id: Reference to crossing(id).
            judge: Name or ID of the judge (human, agent, or rule).
            judge_kind: One of 'rule', 'human', 'agent'.
            decision: One of 'approve', 'reject', 'escalate'.
            rationale: Optional explanation for the decision.
        """
        raise NotImplementedError("write_judgment — owned by Story B, GitHub issue #3")

    def read_experiments(self, filter: dict | None = None) -> list[dict]:
        """Read experiment records, optionally filtered.

        Args:
            filter: Optional dict of column=value constraints.

        Returns:
            List of experiment dicts with all columns.
        """
        raise NotImplementedError("read_experiments — owned by Story B, GitHub issue #3")
