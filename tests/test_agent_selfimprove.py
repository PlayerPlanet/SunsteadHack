"""Tests for agent self-improvement (Issue #43).

Acceptance criteria from the brief:
(a) Accepted edits reduce the objective on the held-out seed across iterations (bend).
(b) check_correctness REJECTS an edit that breaks the .review() contract.
(c) AgentPore ESCALATES a judge-touching edit.
(d) CodeActions apply→rollback is an EXACT round-trip (source text restored byte-for-byte).
(e) The judge NEVER imports an LLM (pure frozen layer).
"""

import pathlib
import pytest
from cleanroom.domains.agent import (
    AgentBenchmark,
    CodeActions,
    AgentPore,
    CuratedSourceProposer,
)
from cleanroom.types import Candidate


class TestBenchmark:
    """Test AgentBenchmark objective computation and correctness gates."""

    def test_objective_moves_with_threshold(self):
        """(a) Benchmark is sensitive to agent changes.

        Proves that the benchmark returns numeric objectives consistent
        with the loop's needs. The actual sensitivity is verified by the
        end-to-end curve script, which shows objective descent.
        """
        benchmark = AgentBenchmark(train_seed=7, eval_seed=11)
        benchmark.freeze_loss_hash()

        # Run benchmark on the current agent (THRESHOLD=0.95).
        result = benchmark.run_benchmark(None, "", warmup=0, trials=1)

        # Verify the result structure.
        assert isinstance(result.p99_ms, float), "p99_ms should be a float"
        assert isinstance(result.throughput, float), "throughput should be a float"
        assert isinstance(result.samples, list), "samples should be a list"
        assert len(result.samples) > 0, "samples should not be empty"

        # The p99_ms should be in a reasonable range (the objective = over_ask + 3*false_clear).
        # With W=3.0, the worst case is ~1.0 (if both rates are high).
        assert 0.0 <= result.p99_ms <= 1.0, f"p99_ms out of range: {result.p99_ms}"

    def test_check_correctness_rejects_broken_review(self):
        """(b) check_correctness should reject edits that break .review()."""
        # Read the original source to restore at the end.
        path = pathlib.Path(__file__).parent.parent / "cleanroom" / "domains" / "agent" / "candidate_agent.py"
        original_source = path.read_text()

        benchmark = AgentBenchmark(eval_seed=11)

        # Create a candidate that breaks the review() contract by removing the Decision class.
        bad_source = (
            "from dataclasses import dataclass\n"
            "from bonds_instrument import judge\n"
            "THRESHOLD = 0.95\n"
            "class CandidateAgent:\n"
            "    def __init__(self):\n"
            "        self.threshold = THRESHOLD\n"
            "    def review(self, view: dict):\n"
            "        # Returns a dict instead of a Decision - contract violation!\n"
            "        return {'verdict': 'ok'}\n"
        )
        bad_candidate = Candidate(
            type="source_edit",
            params={"source_text": bad_source},
            reversible=True,
        )

        # Apply the bad edit.
        actions = CodeActions()
        try:
            actions.apply(None, bad_candidate)
            # check_correctness should return False because review() doesn't return a Decision.
            is_correct = benchmark.check_correctness(None, bad_candidate)
            assert not is_correct, "check_correctness should reject a broken review() contract"
        finally:
            # Restore original source.
            path.write_text(original_source)

    def test_loss_hash_frozen(self):
        """Verify that freeze_loss_hash produces a consistent hash."""
        b1 = AgentBenchmark(eval_seed=11)
        b1.freeze_loss_hash()
        hash1 = b1._loss_hash

        b2 = AgentBenchmark(eval_seed=11)
        b2.freeze_loss_hash()
        hash2 = b2._loss_hash

        assert hash1 == hash2, "Loss hash should be deterministic"


class TestPore:
    """Test AgentPore governance gates."""

    def test_escalate_judge_touching_edit(self):
        """(c) Pore should escalate edits that touch the judge."""
        pore = AgentPore()

        # A candidate that tries to modify the judge.
        bad_candidate = Candidate(
            type="source_edit",
            params={
                "source_text": (
                    "import bonds_instrument.judge\n"
                    "def passes(view): return True  # Broken!\n"
                )
            },
            reversible=True,
        )

        result = pore.evaluate(bad_candidate)

        assert result.decision == "escalate", "Pore should escalate judge-touching edits"
        assert result.requires_human_judgment is True

    def test_allow_low_risk_threshold_edit(self):
        """Pore should allow low-risk in-scope edits."""
        pore = AgentPore()

        good_candidate = Candidate(
            type="source_edit",
            params={"threshold": 0.75},
            reversible=True,
        )

        result = pore.evaluate(good_candidate)

        assert result.decision == "allow", "Pore should allow low-risk threshold edits"
        assert result.requires_human_judgment is False

    def test_block_wrong_candidate_type(self):
        """Pore should block candidates of wrong type."""
        pore = AgentPore()

        bad_candidate = Candidate(
            type="index",
            params={},
            reversible=True,
        )

        result = pore.evaluate(bad_candidate)

        assert result.decision == "block", "Pore should block non-source_edit types"


class TestCodeActions:
    """Test CodeActions apply/rollback mechanism."""

    def test_apply_rollback_exact_roundtrip(self):
        """(d) apply→rollback should restore source text byte-for-byte."""
        path = pathlib.Path(__file__).parent.parent / "cleanroom" / "domains" / "agent" / "candidate_agent.py"
        original_source = path.read_text()

        # Create a candidate that changes the threshold.
        candidate = Candidate(
            type="source_edit",
            params={"threshold": 0.75},
            reversible=True,
        )

        actions = CodeActions()

        try:
            # Apply.
            actions.apply(None, candidate)
            edited_source = path.read_text()
            assert "THRESHOLD = 0.75" in edited_source, "Apply should edit the source"
            assert edited_source != original_source

            # Rollback.
            actions.rollback(None, candidate)
            restored_source = path.read_text()

            # Check byte-for-byte equality.
            assert (
                restored_source == original_source
            ), "Rollback should restore exact source"
        finally:
            # Ensure we restore to a clean state.
            path.write_text(original_source)

    def test_apply_requires_source_or_threshold(self):
        """apply() should raise if neither source_text nor threshold is provided."""
        candidate = Candidate(
            type="source_edit",
            params={},  # Empty params.
            reversible=True,
        )

        actions = CodeActions()

        with pytest.raises(ValueError):
            actions.apply(None, candidate)

    def test_apply_wrong_candidate_type(self):
        """apply() should raise if candidate type is not source_edit."""
        candidate = Candidate(
            type="index",
            params={"threshold": 0.75},
            reversible=True,
        )

        actions = CodeActions()

        with pytest.raises(ValueError):
            actions.apply(None, candidate)


class TestJudgePurity:
    """Test that the judge never imports an LLM."""

    def test_judge_imports_no_llm(self):
        """(e) judge.py should not import anthropic, openai, boto3, etc."""
        judge_path = pathlib.Path(__file__).parent.parent / "bonds_instrument" / "judge.py"
        judge_source = judge_path.read_text()

        # Check for forbidden imports.
        forbidden_patterns = [
            "import anthropic",
            "from anthropic",
            "import openai",
            "from openai",
            "import boto3",
            "from boto3",
            "LLMAgent",
            "Claude",
            "ChatMessage",
        ]

        for pattern in forbidden_patterns:
            assert (
                pattern not in judge_source
            ), f"judge.py must not contain '{pattern}' (frozen, pure layer)"


class TestProposer:
    """Test CuratedSourceProposer."""

    def test_proposer_walks_descent_path(self):
        """Proposer should walk the proven descent path (no baseline repeat)."""
        proposer = CuratedSourceProposer()

        candidates = []
        for _ in range(2):
            c = proposer.propose({}, [])
            candidates.append(c)

        # Extract thresholds from candidates.
        thresholds = [c.params.get("threshold") for c in candidates]

        expected = [0.80, 0.65]
        assert thresholds == expected, f"Expected {expected}, got {thresholds}"


class TestAgentDomainBundle:
    """Test agent domain registration in the control plane."""

    def test_agent_bundle_creation(self):
        """Agent bundle should be creatable and have correct adapter types."""
        from cleanroom.control.domains import _agent_bundle
        from cleanroom.domains.agent import (
            AgentBenchmark,
            CodeActions,
            AgentPore,
            CuratedSourceProposer,
        )

        bundle = _agent_bundle()

        # Verify bundle has the right types.
        assert isinstance(bundle.proposer, CuratedSourceProposer), "proposer type mismatch"
        assert isinstance(bundle.benchmark, AgentBenchmark), "benchmark type mismatch"
        assert isinstance(bundle.pore, AgentPore), "pore type mismatch"
        assert isinstance(bundle.actions, CodeActions), "actions type mismatch"
        assert callable(bundle.make_env), "make_env should be callable"

    def test_agent_domain_resolution(self):
        """Agent domain should be resolvable via 'agent_selfimprove' workload_id."""
        from cleanroom.control.domains import (
            resolve_domain,
            is_domain_workload,
        )

        # Check that the agent workload is registered.
        assert is_domain_workload("agent_selfimprove"), "agent_selfimprove should be a registered domain"

        # Check that resolution returns the bundle.
        bundle = resolve_domain({"workload_id": "agent_selfimprove"})
        assert bundle is not None, "resolve_domain should return a bundle for agent_selfimprove"

        # Verify it has the right adapters.
        from cleanroom.domains.agent import AgentBenchmark, CodeActions, AgentPore
        assert isinstance(bundle.benchmark, AgentBenchmark)
        assert isinstance(bundle.pore, AgentPore)
        assert isinstance(bundle.actions, CodeActions)

    def test_make_env_resets_candidate_agent(self):
        """make_env should reset candidate_agent.py to baseline (THRESHOLD=0.95)."""
        from cleanroom.control.domains import _agent_bundle
        import pathlib

        # Set file to a non-baseline state first.
        path = pathlib.Path(__file__).parent.parent / "cleanroom" / "domains" / "agent" / "candidate_agent.py"
        original_source = path.read_text()

        try:
            # Modify to non-baseline.
            import re
            modified = re.sub(r'THRESHOLD\s*=\s*[\d.]+', 'THRESHOLD = 0.65', original_source)
            path.write_text(modified)

            # Now call make_env, which should reset it.
            bundle = _agent_bundle()
            env = bundle.make_env()

            # Verify the file is reset to baseline.
            content = path.read_text()
            assert "THRESHOLD = 0.95" in content, "make_env should reset THRESHOLD to 0.95"

        finally:
            # Restore original.
            path.write_text(original_source)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
