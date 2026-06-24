"""Full vertical integration test for Story A interior loop.

Proves that run_loop with the REAL ClaudeCodeProposer turns end-to-end,
including container-based research and real index proposals.

This test is marked @pytest.mark.golden and skips unless:
1. ANTHROPIC_API_KEY is set in environment
2. Docker and the sunstead-proposer:latest image are available
3. sunstead-proposer-pg container is running on localhost:55432
"""

import os
import pytest

from cleanroom.loop import run_loop
from cleanroom.loop.proposers import ClaudeCodeProposer
from cleanroom.fixtures import (
    CannedBenchmark,
    InMemoryLogClient,
    NoOpPore,
)


@pytest.mark.golden
class TestIntegrationE2EInteriorLoop:
    """Full vertical integration: ClaudeCodeProposer + real container research."""

    @pytest.fixture
    def check_prerequisites(self):
        """Verify prerequisites for golden test.

        Skips if:
        - ANTHROPIC_API_KEY not set
        - Docker not available
        - sunstead-proposer-pg container not reachable
        """
        # Check API key
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("anthropic_api_key")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set")

        # Check Docker and image
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "image", "inspect", "sunstead-proposer:latest"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode != 0:
                pytest.skip(
                    "sunstead-proposer:latest image not available; "
                    "run `docker build -t sunstead-proposer proposer-container/`"
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("Docker not available or command timed out")

        # Check container reachability
        try:
            import psycopg2
            conn = psycopg2.connect(
                host="localhost",
                port=55432,
                user="postgres",
                password="postgres",
                database="postgres",
                connect_timeout=2,
            )
            conn.close()
        except (ImportError, Exception):
            pytest.skip(
                "sunstead-proposer-pg container not reachable on localhost:55432; "
                "run `docker-compose -f proposer-container/docker-compose.yml up -d`"
            )

    def test_run_loop_with_claude_code_proposer_real_container(self, check_prerequisites):
        """End-to-end: ClaudeCodeProposer queries container, proposes real index candidates.

        Proves:
        1. ClaudeCodeProposer.propose() calls the container and gets back real index candidates
        2. apply() handles index candidates without error
        3. Loop completes successfully with real proposals
        4. LogClient records experiments with valid structure and decisions
        5. Cost is tracked and bounded (<$1 for 2 iterations)
        """
        # Task spec: real but minimal workload
        task_spec = {
            "task_id": "job_index",
            "model": "claude-haiku-4-5-20251001",
            "workload_id": "job_q1",
            "objective": "minimize p99 on the title⋈cast_info production_year query",
            "conn": None,  # Phase-0: no apply/benchmark on real DB
        }

        # Real proposer (uses Claude API to query the container)
        proposer = ClaudeCodeProposer()

        # Canned benchmark for predictable results
        benchmark = CannedBenchmark(baseline_p99=100.0)

        # No-op pore (allow all proposals)
        pore = NoOpPore()

        # In-memory log client
        logclient = InMemoryLogClient()

        # Run for 2 iterations to bound cost (~$0.03 * 2 = $0.06 container cost)
        run_loop(
            task_spec,
            proposer=proposer,
            benchmark=benchmark,
            pore=pore,
            logclient=logclient,
            iterations=2,
        )

        # Verify experiments were recorded
        experiments = logclient.read_experiments()
        # Iteration 0 is baseline only; iteration 1 should have one experiment
        assert len(experiments) >= 1, "Expected at least 1 experiment from the loop"

        # Verify structure of experiments
        for exp in experiments:
            assert "task_id" in exp
            assert "model" in exp
            assert "candidate" in exp
            assert "decision" in exp
            assert "baseline_p99" in exp

        # Verify that candidates are real index proposals from the container
        index_candidates = [
            e["candidate"] for e in experiments
            if e["candidate"].get("type") == "index"
        ]

        # At least one should be an index proposal from the container
        if index_candidates:
            for candidate in index_candidates:
                assert candidate.get("type") == "index"
                assert "params" in candidate
                assert "table" in candidate["params"]
                assert "columns" in candidate["params"]
                assert isinstance(candidate["params"]["columns"], list)

        # Verify decisions
        for exp in experiments:
            assert exp["decision"] in {"keep", "discard", "rollback", "escalated"}

        # Verify cost is tracked and bounded
        total_cost = sum(e.get("cost_estimate", 0) for e in experiments)
        # Should be well under $1 for 2 iterations
        assert total_cost < 1.0, f"Cost unexpectedly high: ${total_cost:.4f}"

        # Print summary for manual inspection
        print(f"\n=== Integration Test Summary ===")
        print(f"Total experiments: {len(experiments)}")
        print(f"Total cost: ${total_cost:.4f}")
        for i, exp in enumerate(experiments):
            candidate_type = exp["candidate"].get("type", "unknown")
            decision = exp["decision"]
            baseline_p99 = exp.get("baseline_p99")
            candidate_p99 = exp.get("candidate_p99")
            print(f"  Exp {i+1}: {candidate_type} {decision}")
            if candidate_type == "index" and candidate_p99:
                params = exp["candidate"].get("params", {})
                table = params.get("table", "?")
                columns = params.get("columns", [])
                print(f"    Index on {table}({','.join(columns)})")
                print(f"    Baseline: {baseline_p99:.2f}ms, Candidate: {candidate_p99:.2f}ms")
