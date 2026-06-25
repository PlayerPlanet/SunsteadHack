"""Tests for BYO-Agent judge — verify no LLM client imports and correctness checks."""

import pytest

from cleanroom.domains.byo_agent.judge import BYOAgentBenchmark
from cleanroom.domains.byo_agent.agentcore_client import StubAgent
from cleanroom.types import Candidate


class TestBYOAgentNoLLMImportInJudge:
    """Issue #28: Verify judge imports NO LLM client."""

    def test_judge_module_has_no_anthropic_imports(self):
        """Scan the judge module for forbidden import statements."""
        import cleanroom.domains.byo_agent.judge as judge_module
        import inspect

        source = inspect.getsource(judge_module)

        # Check for actual import statements, not just mentions in comments/strings.
        forbidden_imports = [
            "import anthropic",
            "from anthropic",
            "import openai",
            "from openai",
            "import boto3",
            "from boto3",
            "import google.generativeai",
            "import cohere",
        ]

        for import_stmt in forbidden_imports:
            assert (
                import_stmt not in source
            ), f"Judge module must not contain '{import_stmt}' (Issue #28 paradox)"


class TestBYOAgentBenchmark:
    """Test the judge/benchmark implementation."""

    def test_run_benchmark_with_stub_agent(self):
        """Better configs should lower error rate."""
        bad_config = {"system_prompt": "answer", "temperature": 1.5}
        good_config = {"system_prompt": "You are an expert. Answer carefully.", "temperature": 0.5}

        agent = StubAgent()

        eval_data = {
            "train": [{"input": "q1", "expected": "a1"}, {"input": "q2", "expected": "a2"}],
            "holdout": [{"input": "q3", "expected": "a3"}, {"input": "q4", "expected": "a4"}],
        }

        env_bad = {
            "_agent": agent,
            "_eval": eval_data,
            "_cur_config": bad_config,
            "_grader": ("exact", BYOAgentBenchmark._exact_grader),
            "_loss_hash": "test",
        }

        env_good = {
            "_agent": agent,
            "_eval": eval_data,
            "_cur_config": good_config,
            "_grader": ("exact", BYOAgentBenchmark._exact_grader),
            "_loss_hash": "test",
        }

        benchmark = BYOAgentBenchmark()
        bad_result = benchmark.run_benchmark(env_bad, "test", trials=2)
        good_result = benchmark.run_benchmark(env_good, "test", trials=2)

        # Good config should have lower error rate (p99_ms overloaded as error_rate).
        assert (
            good_result.p99_ms <= bad_result.p99_ms
        ), "Good config should have lower error rate"

    def test_check_correctness_detects_tamper(self):
        """check_correctness should reject grader/eval tampering."""
        benchmark = BYOAgentBenchmark()

        # Compute the correct loss hash for this env.
        eval_dict = {"train": [], "holdout": []}
        grader = ("exact", BYOAgentBenchmark._exact_grader)
        loss_hash = benchmark._compute_loss_hash({
            "_eval": eval_dict,
            "_grader": grader,
        })

        env = {
            "_agent": StubAgent(),
            "_eval": eval_dict,
            "_grader": grader,
            "_loss_hash": loss_hash,
        }

        candidate_ok = Candidate(
            type="agent_config", params={"config_delta": {"temperature": 0.5}}, reversible=True
        )

        candidate_tamper = Candidate(
            type="agent_config", params={"config_delta": {"_grader": "HACKED"}}, reversible=True
        )

        assert benchmark.check_correctness(env, candidate_ok) is True
        assert benchmark.check_correctness(env, candidate_tamper) is False

    def test_is_within_noise_delegates_correctly(self):
        """is_within_noise should delegate to shared statistical gate."""
        benchmark = BYOAgentBenchmark()

        baseline = [0.5, 0.5, 0.5, 0.5, 0.5]
        candidate_same = [0.5, 0.5, 0.5, 0.5, 0.5]
        candidate_much_better = [0.1, 0.1, 0.1, 0.1, 0.1]

        # Identical samples should be within noise.
        assert benchmark.is_within_noise(baseline, candidate_same) is True

        # Much lower error should NOT be within noise.
        assert benchmark.is_within_noise(baseline, candidate_much_better) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
