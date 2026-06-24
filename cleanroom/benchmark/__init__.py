"""Benchmark and correctness evaluation.

Story B (GitHub issue #3) owns the production benchmark harness and correctness
checker. This module defines the contract so Story A can invoke it from the loop.
"""

from cleanroom.types import Candidate, Result


def run_benchmark(conn, workload_id: str, *, warmup: int = 5, trials: int = 10) -> Result:
    """Execute a benchmark on the given connection with the candidate configuration.

    Args:
        conn: A database connection object.
        workload_id: Identifier for the workload to benchmark.
        warmup: Number of warmup iterations before measurement.
        trials: Number of measurement trials.

    Returns:
        A Result with p99_ms, throughput, cost_estimate, and samples.

    Raises:
        NotImplementedError: Story B owns this implementation.
    """
    raise NotImplementedError("run_benchmark — owned by Story B, GitHub issue #3")


def check_correctness(conn, candidate: Candidate) -> bool:
    """Verify that the candidate produces correct results.

    Args:
        conn: A database connection object.
        candidate: The candidate to validate.

    Returns:
        True if correctness check passes, False otherwise.

    Raises:
        NotImplementedError: Story B owns this implementation.
    """
    raise NotImplementedError("check_correctness — owned by Story B, GitHub issue #3")


def is_within_noise(baseline_samples: list[float], candidate_samples: list[float]) -> bool:
    """Determine if candidate performance is within noise of baseline.

    Args:
        baseline_samples: Individual samples from baseline run.
        candidate_samples: Individual samples from candidate run.

    Returns:
        True if candidate is statistically indistinguishable from baseline.

    Raises:
        NotImplementedError: Story B owns this implementation.
    """
    raise NotImplementedError("is_within_noise — owned by Story B, GitHub issue #3")
