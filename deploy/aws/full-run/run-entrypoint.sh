#!/bin/bash
# Phase-2 Full-Run Entrypoint
# Executes the complete optimization loop for a single task.
#
# Environment variables (injected by ECS task definition):
#   TASK_ID         - Task identifier
#   MODEL           - Claude model to use
#   ITERATIONS      - Number of optimization iterations
#   DB_DSN          - Read-only Postgres DSN (from Secrets Manager)
#   ANTHROPIC_API_KEY - API key (from Secrets Manager)

set -e

TASK_ID="${TASK_ID:-}"
MODEL="${MODEL:-claude-opus-4-20250805}"
ITERATIONS="${ITERATIONS:-1}"

if [ -z "$TASK_ID" ]; then
    echo '{"error":"TASK_ID environment variable not set"}'
    exit 1
fi

echo "===== SunsteadHack Full-Run Loop ====="
echo "Task: $TASK_ID"
echo "Model: $MODEL"
echo "Iterations: $ITERATIONS"
echo ""

# TODO(Story B integration):
# Replace the fixture objects below with the real implementations once Story B lands:
#   - cleanroom.loop.proposers.Proposer → actual proposer
#   - cleanroom.benchmark.Benchmark → actual benchmark harness
#   - cleanroom.pore.Pore → actual escalation gate
#   - cleanroom.logclient.LogClient → actual log DB client
#
# The loop signature (cleanroom.loop.run_loop) is frozen; only the component
# implementations change.

python3 << 'PYTHON_EOF'
import os
import sys
from typing import Optional

# Import the loop and required types
from cleanroom import loop
from cleanroom.types import Candidate


# FIXTURE IMPLEMENTATIONS (TODO: Replace with Story B)
# These are placeholder objects that allow the loop to run and prove the
# pipeline end-to-end, without real ML harness components.


class FakeProposer:
    """Fixture proposer that returns a hardcoded index candidate."""

    def propose(self, task_spec: dict) -> Optional[Candidate]:
        """Return a dummy candidate."""
        return Candidate(
            type="index",
            params={
                "table": "cast_info",
                "columns": ["movie_id"],
            },
            reversible=True,
        )


class FakeBenchmark:
    """Fixture benchmark that returns mock measurements."""

    def benchmark(
        self,
        task_spec: dict,
        candidate: Candidate,
    ) -> tuple[float, float, bool]:
        """Return (baseline_p99, candidate_p99, correctness_ok)."""
        # Mock: small improvement (baseline 100ms → candidate 90ms)
        return 100.0, 90.0, True


class FakePore:
    """Fixture pore gate that always approves candidates."""

    def escalate(
        self,
        task_spec: dict,
        candidate: Candidate,
        baseline_p99: float,
        candidate_p99: float,
        cost_estimate: float,
    ) -> str:
        """Return decision: 'apply', 'discard', or 'escalate'."""
        # Fixture: always approve
        return "apply"


class FakeLogClient:
    """Fixture log client that writes to stdout."""

    def write_experiment(
        self,
        task_id: str,
        model: str,
        drift_level: float,
        candidate: dict,
        baseline_p99: Optional[float],
        candidate_p99: Optional[float],
        cost_estimate: Optional[float],
        correctness_ok: Optional[bool],
        within_noise: Optional[bool],
        decision: str,
    ) -> int:
        """Log an experiment and return exp_id."""
        import json

        exp_log = {
            "task_id": task_id,
            "model": model,
            "candidate": candidate,
            "baseline_p99": baseline_p99,
            "candidate_p99": candidate_p99,
            "decision": decision,
        }
        print(f"EXPERIMENT: {json.dumps(exp_log)}")
        return 1  # Fake exp_id


# Main
if __name__ == "__main__":
    task_id = os.environ.get("TASK_ID", "")
    model = os.environ.get("MODEL", "claude-opus-4-20250805")
    iterations = int(os.environ.get("ITERATIONS", "1"))

    print(f"Task: {task_id}, Model: {model}, Iterations: {iterations}")
    print()

    # Fixture task spec
    task_spec = {
        "task_id": task_id,
        "workload": "IMDB-shaped query: optimize for latency",
    }

    # TODO(Story B integration): Replace with real components:
    # proposer = cleanroom.loop.proposers.ContainerProposer(...)
    # benchmark = cleanroom.benchmark.Benchmark(...)
    # pore = cleanroom.pore.Pore(...)
    # logclient = cleanroom.logclient.LogClient(...)

    proposer = FakeProposer()
    benchmark = FakeBenchmark()
    pore = FakePore()
    logclient = FakeLogClient()

    # Run the loop
    try:
        loop.run_loop(
            task_spec,
            proposer=proposer,
            benchmark=benchmark,
            pore=pore,
            logclient=logclient,
            iterations=iterations,
        )
        print("✓ Loop completed successfully")
    except Exception as e:
        print(f"✗ Loop failed: {e}", file=sys.stderr)
        sys.exit(1)

PYTHON_EOF

echo "===== Full-Run Complete ====="
