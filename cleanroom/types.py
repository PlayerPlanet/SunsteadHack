"""Frozen shared contract types — changes require sign-off from issues #2/#3/#4.

This module defines immutable dataclasses that form the core contract between
the loop (Story A), benchmark/pore/logclient (Story B), and boundary/dashboard
(Story C). Do not add, remove, or rename fields without co-author consensus.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Candidate:
    """A proposed optimization candidate.

    Fields:
        type: The kind of candidate (e.g., 'index', 'parameter', 'algorithm').
        params: A dictionary of candidate-specific parameters.
        reversible: Whether this candidate can be rolled back.
    """
    type: str
    params: dict
    reversible: bool


@dataclass(frozen=True, slots=True)
class Result:
    """Benchmark result for a single candidate.

    Fields:
        p99_ms: 99th percentile latency in milliseconds.
        throughput: Throughput (e.g., queries per second).
        cost_estimate: Estimated cost for this candidate.
        samples: List of individual sample measurements (for noise detection).
    """
    p99_ms: float
    throughput: float
    cost_estimate: float
    samples: list[float]


@dataclass(frozen=True, slots=True)
class PoreResult:
    """Result of a pore (proof-of-risk-evaluation) assessment.

    Fields:
        pore: Identifier for the pore rule that evaluated this candidate.
        risk_level: One of 'low', 'medium', 'high'.
        requires_human_judgment: Whether this candidate needs human review.
        decision: One of 'allow', 'block', 'escalate'.
    """
    pore: str
    risk_level: str
    requires_human_judgment: bool
    decision: str
