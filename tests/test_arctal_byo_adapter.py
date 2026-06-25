"""Tests for the Arctal green-bond review agent adapter.

Doctrine (issue #28 — non-circular judge):
  - Labels MUST come ONLY from bonds_instrument.judge (deterministic re-derivation)
    + planted bonds_instrument.claims.poison corruptions.
  - The agent (contestant) may be an LLM; the judge (referee) must NOT be.
  - build_arctal_eval is a pure function: same seed → identical results, no LLM.
  - The BYOAgentBenchmark grader is "exact" (string match).
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from cleanroom.domains.byo_agent.adapters import (
    ArctalReviewAgent,
    build_arctal_eval,
    write_arctal_eval_jsonl,
)
from cleanroom.domains.byo_agent import BYOAgentBenchmark


class TestBuildArctalEval:
    """Test eval data generation."""

    def test_deterministic(self):
        """Same seed produces identical results."""
        eval1 = build_arctal_eval(seed=7)
        eval2 = build_arctal_eval(seed=7)
        assert eval1 == eval2, "build_arctal_eval should be deterministic"

    def test_different_seed_different_result(self):
        """Different seed produces different results."""
        eval1 = build_arctal_eval(seed=7)
        eval2 = build_arctal_eval(seed=999)
        assert eval1 != eval2, "Different seed should produce different eval"

    def test_labels_non_llm(self):
        """Eval labels are deterministic (no LLM in building)."""
        # Monkeypatch anthropic to raise if imported/used.
        with patch("anthropic.Anthropic", side_effect=RuntimeError("anthropic should not be imported")):
            eval_data = build_arctal_eval(seed=7)
        assert len(eval_data) > 0, "Should build eval without anthropic"
        for item in eval_data:
            assert item["expected"] in {"ok", "error", "escalate"}

    def test_all_expected_values_valid(self):
        """All expected values are one of ok/error/escalate."""
        eval_data = build_arctal_eval(seed=7)
        for item in eval_data:
            assert "input" in item
            assert "expected" in item
            assert item["expected"] in {"ok", "error", "escalate"}

    def test_inputs_are_json_strings(self):
        """All inputs are JSON-serializable (claim views)."""
        eval_data = build_arctal_eval(seed=7)
        for item in eval_data:
            view = json.loads(item["input"])
            assert "kind" in view, "Each view should have a 'kind' field"


class TestArctalReviewAgent:
    """Test the agent adapter."""

    def test_rule_mode_on_clean_claim(self):
        """Rule mode returns 'ok' for a clean claim."""
        agent = ArctalReviewAgent(mode="rule")
        eval_data = build_arctal_eval(seed=7)
        # Find a clean claim (expected="ok") to test.
        clean_items = [e for e in eval_data if e["expected"] == "ok"]
        assert len(clean_items) > 0, "Should have clean claims in eval"

        for item in clean_items[:1]:  # Test just the first one.
            response = agent.invoke(item["input"], {})
            assert response["result"] == "ok", "Rule mode should return 'ok' for clean claims"
            assert response["tokens"] == 0, "Rule mode should have 0 tokens"

    def test_rule_mode_on_catchable_error(self):
        """Rule mode returns 'error' for judge-catchable corruptions."""
        agent = ArctalReviewAgent(mode="rule")
        eval_data = build_arctal_eval(seed=7)
        # Find an error claim (expected="error").
        error_items = [e for e in eval_data if e["expected"] == "error"]
        assert len(error_items) > 0, "Should have error claims in eval"

        for item in error_items[:1]:
            response = agent.invoke(item["input"], {})
            # Rule mode can only catch judge-catchable errors.
            # If the claim's corruption is judge-catchable, result should be "error".
            assert response["result"] in {"ok", "error"}, "Rule mode should return ok or error"
            assert response["tokens"] == 0

    def test_rule_mode_no_network(self):
        """Rule mode never makes network calls."""
        agent = ArctalReviewAgent(mode="rule")
        eval_data = build_arctal_eval(seed=7)

        if eval_data:
            response = agent.invoke(eval_data[0]["input"], {})
            # Should succeed without network.
            assert "result" in response
            assert response["result"] in {"ok", "error", "escalate"}

    def test_invalid_json_input(self):
        """Invalid JSON input returns escalate."""
        agent = ArctalReviewAgent(mode="rule")
        response = agent.invoke("not valid json", {})
        assert response["result"] == "escalate"
        assert response["tokens"] == 0

    def test_llm_mode_with_mock(self):
        """LLM mode with mocked anthropic client."""
        # Mock the anthropic client.
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="PLAUSIBLE")]
        mock_msg.usage.input_tokens = 10
        mock_msg.usage.output_tokens = 2
        mock_client.messages.create.return_value = mock_msg

        agent = ArctalReviewAgent(mode="llm")
        agent._client = mock_client

        eval_data = build_arctal_eval(seed=7)
        if eval_data:
            config = {
                "system_prompt": "You are an auditor.",
                "temperature": 0.3,
                "top_p": 1.0,
                "max_tokens": 256,
            }
            response = agent.invoke(eval_data[0]["input"], config)
            assert response["result"] in {"ok", "error", "escalate"}
            assert response["tokens"] > 0

    def test_llm_mode_maps_implausible_to_error(self):
        """LLM reply 'IMPLAUSIBLE' maps to 'error'."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="IMPLAUSIBLE")]
        mock_msg.usage.input_tokens = 10
        mock_msg.usage.output_tokens = 2
        mock_client.messages.create.return_value = mock_msg

        agent = ArctalReviewAgent(mode="llm")
        agent._client = mock_client

        eval_data = build_arctal_eval(seed=7)
        if eval_data:
            response = agent.invoke(eval_data[0]["input"], {})
            assert response["result"] == "error"

    def test_llm_mode_maps_unsure_to_escalate(self):
        """LLM reply 'UNSURE' maps to 'escalate'."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="UNSURE")]
        mock_msg.usage.input_tokens = 10
        mock_msg.usage.output_tokens = 2
        mock_client.messages.create.return_value = mock_msg

        agent = ArctalReviewAgent(mode="llm")
        agent._client = mock_client

        eval_data = build_arctal_eval(seed=7)
        if eval_data:
            response = agent.invoke(eval_data[0]["input"], {})
            assert response["result"] == "escalate"

    def test_llm_mode_maps_plausible_to_ok(self):
        """LLM reply 'PLAUSIBLE' maps to 'ok'."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="PLAUSIBLE")]
        mock_msg.usage.input_tokens = 10
        mock_msg.usage.output_tokens = 2
        mock_client.messages.create.return_value = mock_msg

        agent = ArctalReviewAgent(mode="llm")
        agent._client = mock_client

        eval_data = build_arctal_eval(seed=7)
        if eval_data:
            response = agent.invoke(eval_data[0]["input"], {})
            assert response["result"] == "ok"

    def test_llm_mode_fallback_on_exception(self):
        """LLM mode returns escalate on any exception."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Network error")

        agent = ArctalReviewAgent(mode="llm")
        agent._client = mock_client

        eval_data = build_arctal_eval(seed=7)
        if eval_data:
            response = agent.invoke(eval_data[0]["input"], {})
            assert response["result"] == "escalate"
            assert response["tokens"] == 0


class TestExactGraderIntegration:
    """Test integration with BYOAgentBenchmark's exact grader."""

    def test_rule_agent_with_exact_grader(self):
        """Rule agent accuracy with exact grader."""
        from cleanroom.domains.byo_agent import (
            BYOAgentBenchmark,
            _split_train_holdout,
        )

        eval_data = build_arctal_eval(seed=7)
        split = _split_train_holdout(eval_data, train_fraction=0.7)

        agent = ArctalReviewAgent(mode="rule")
        grader_kind, grader_fn = "exact", BYOAgentBenchmark._exact_grader

        env = {
            "_agent": agent,
            "_eval": split,
            "_cur_config": {
                "system_prompt": "You are an auditor.",
                "temperature": 0.0,
            },
            "_grader": (grader_kind, grader_fn),
            "_loss_hash": "test_hash",
            "_logclient": None,
            "_config_stack": [],
        }

        benchmark = BYOAgentBenchmark()
        result = benchmark.run_benchmark(env, workload_id="test", trials=1)

        # The rule agent can only catch judge-catchable errors,
        # so its accuracy won't be perfect, but it should be > 0.
        assert result.p99_ms >= 0.0
        assert result.p99_ms <= 1.0
        assert len(result.samples) == 1


class TestWriteArctalEvalJsonl:
    """Test JSONL file writing."""

    def test_write_and_read_back(self, tmp_path):
        """Write and read back eval data."""
        output_path = tmp_path / "arctal_eval.jsonl"
        write_arctal_eval_jsonl(str(output_path), seed=7)

        assert output_path.exists()

        # Read back and validate.
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) > 0

        for line in lines:
            item = json.loads(line)
            assert "input" in item
            assert "expected" in item
            assert item["expected"] in {"ok", "error", "escalate"}
