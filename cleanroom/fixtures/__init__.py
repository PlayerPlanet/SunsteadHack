"""Fixtures for Phase-0 testing and development without real infrastructure.

These are REAL, FULLY WORKING implementations so Stories A and C can build
and test end-to-end against dummy data.
"""

import statistics
from collections import defaultdict

from cleanroom.types import Candidate, Result, PoreResult


class CannedBenchmark:
    """A deterministic benchmark that returns improving results as the loop progresses.

    The p99 latency decreases as successive candidates are proposed (driven by
    the proposer's internal state or candidate.params), creating a downward curve
    that demonstrates end-to-end loop execution.
    """

    def __init__(self, baseline_p99: float = 100.0):
        """Initialize the canned benchmark.

        Args:
            baseline_p99: Starting p99 latency in milliseconds.
        """
        self.baseline_p99 = baseline_p99
        self.call_count = 0
        self.improvement_rate = 0.95  # Each call improves by 5%

    def run_benchmark(
        self, conn, workload_id: str, *, warmup: int = 5, trials: int = 10
    ) -> Result:
        """Run a deterministic benchmark that improves over time.

        Args:
            conn: Ignored (no real connection needed).
            workload_id: Ignored (deterministic behavior).
            warmup: Ignored.
            trials: Number of samples to generate.

        Returns:
            A Result with decreasing p99 and synthetic throughput.
        """
        self.call_count += 1
        # Decrease p99 with each call
        current_p99 = self.baseline_p99 * (self.improvement_rate ** self.call_count)

        # Generate synthetic samples with slight variation
        samples = [
            current_p99 * (0.95 + (i % 3) * 0.02) for i in range(trials)
        ]

        throughput = 1000.0 / current_p99  # Queries per second (inverse of p99)
        cost_estimate = 10.0 + (0.1 * self.call_count)  # Dummy cost curve

        return Result(
            p99_ms=current_p99,
            throughput=throughput,
            cost_estimate=cost_estimate,
            samples=samples,
        )

    def check_correctness(self, conn, candidate: Candidate) -> bool:
        """Dummy correctness check — always passes.

        Args:
            conn: Ignored.
            candidate: Ignored.

        Returns:
            Always True.
        """
        return True

    def is_within_noise(
        self, baseline_samples: list[float], candidate_samples: list[float]
    ) -> bool:
        """Compare two sample sets using mean and stdev.

        Args:
            baseline_samples: Baseline latency samples.
            candidate_samples: Candidate latency samples.

        Returns:
            True if the mean difference is less than one combined stdev.
        """
        if not baseline_samples or not candidate_samples:
            return True

        baseline_mean = statistics.mean(baseline_samples)
        candidate_mean = statistics.mean(candidate_samples)

        # Compute stdevs, handle single-sample case
        baseline_stdev = (
            statistics.stdev(baseline_samples)
            if len(baseline_samples) > 1
            else 0.0
        )
        candidate_stdev = (
            statistics.stdev(candidate_samples)
            if len(candidate_samples) > 1
            else 0.0
        )

        combined_stdev = (baseline_stdev + candidate_stdev) / 2.0 or 1.0

        # Within noise if |mean_diff| < combined_stdev
        return abs(candidate_mean - baseline_mean) < combined_stdev


class NoOpPore:
    """A minimal pore that always allows candidates.

    Useful for testing the loop without risk gates.
    """

    def evaluate(self, candidate: Candidate) -> PoreResult:
        """Always return low risk and allow decision.

        Args:
            candidate: Ignored.

        Returns:
            A PoreResult with decision='allow', risk_level='low'.
        """
        return PoreResult(
            pore="noop",
            risk_level="low",
            requires_human_judgment=False,
            decision="allow",
        )


class InMemoryLogClient:
    """In-memory implementation of LogClient protocol.

    Stores experiment, crossing, and judgment records in Python lists.
    Suitable for end-to-end testing without a database.
    """

    def __init__(self):
        """Initialize empty in-memory storage."""
        self.experiments = []
        self.crossings = []
        self.judgments = []
        self._experiment_counter = 0
        self._crossing_counter = 0
        self._judgment_counter = 0

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
        """Write an experiment record to memory.

        Returns:
            A synthetic experiment ID (auto-incrementing).
        """
        self._experiment_counter += 1
        record = {
            "id": self._experiment_counter,
            "task_id": task_id,
            "model": model,
            "drift_level": drift_level,
            "candidate": candidate,
            "baseline_p99": baseline_p99,
            "candidate_p99": candidate_p99,
            "cost_estimate": cost_estimate,
            "correctness_ok": correctness_ok,
            "within_noise": within_noise,
            "decision": decision,
        }
        self.experiments.append(record)
        return self._experiment_counter

    def write_crossing(
        self,
        experiment_id: int,
        pore: str,
        risk_level: str,
        requires_human_judgment: bool,
        action: dict,
    ) -> int:
        """Write a crossing record to memory.

        Returns:
            A synthetic crossing ID (auto-incrementing).
        """
        self._crossing_counter += 1
        record = {
            "id": self._crossing_counter,
            "experiment_id": experiment_id,
            "pore": pore,
            "risk_level": risk_level,
            "requires_human_judgment": requires_human_judgment,
            "action": action,
        }
        self.crossings.append(record)
        return self._crossing_counter

    def write_judgment(
        self,
        crossing_id: int,
        judge: str,
        judge_kind: str,
        decision: str,
        rationale: str | None = None,
    ) -> None:
        """Write a judgment record to memory."""
        self._judgment_counter += 1
        record = {
            "id": self._judgment_counter,
            "crossing_id": crossing_id,
            "judge": judge,
            "judge_kind": judge_kind,
            "decision": decision,
            "rationale": rationale,
        }
        self.judgments.append(record)

    def read_experiments(self, filter: dict | None = None) -> list[dict]:
        """Read experiment records, optionally filtered by column=value.

        Args:
            filter: Optional dict of column=value constraints.

        Returns:
            List of matching experiment dicts.
        """
        if not filter:
            return list(self.experiments)

        results = []
        for exp in self.experiments:
            if all(exp.get(k) == v for k, v in filter.items()):
                results.append(exp)
        return results


class DummyProposer:
    """A simple proposer that generates varying candidates.

    Successive calls return candidates with different params, driving the
    CannedBenchmark's improving curve.
    """

    def __init__(self, base_candidate_type: str = "index"):
        """Initialize the dummy proposer.

        Args:
            base_candidate_type: The type of candidates to propose.
        """
        self.base_type = base_candidate_type
        self.proposal_count = 0

    def propose(self, task_spec: dict, history: list) -> Candidate:
        """Generate a candidate whose params vary by history length.

        Args:
            task_spec: Task specification (ignored for dummy).
            history: Previous candidates (drives variation).

        Returns:
            A Candidate with varying params.
        """
        self.proposal_count += 1
        # Vary params by the length of history so successive proposals differ
        return Candidate(
            type=self.base_type,
            params={
                "iteration": self.proposal_count,
                "history_length": len(history),
                "scale_factor": 1.0 + 0.1 * len(history),
            },
            reversible=True,
        )
