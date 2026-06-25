"""Tests for BYO-Agent proposer — verify it never leaks holdout data."""

import pytest

from cleanroom.domains.byo_agent.proposer import ScriptedProposer
from cleanroom.types import Candidate


class TestScriptedProposer:
    """Test the deterministic proposer (used for offline testing)."""

    def test_scripted_proposer_cycles_through_sequence(self):
        """Proposer should cycle through a fixed sequence."""
        sequence = [
            {"system_prompt": "expert"},
            {"temperature": 0.5},
            {"few_shot": []},
        ]
        proposer = ScriptedProposer(sequence)

        task_spec = {"objective": "test"}
        history = []

        # First three calls should return the sequence.
        candidate1 = proposer.propose(task_spec, history)
        assert candidate1.params["config_delta"]["system_prompt"] == "expert"

        candidate2 = proposer.propose(task_spec, history)
        assert candidate2.params["config_delta"]["temperature"] == 0.5

        candidate3 = proposer.propose(task_spec, history)
        assert candidate3.params["config_delta"]["few_shot"] == []

        # Fourth call should cycle back to the first.
        candidate4 = proposer.propose(task_spec, history)
        assert candidate4.params["config_delta"]["system_prompt"] == "expert"

    def test_scripted_proposer_returns_valid_candidates(self):
        """All returned candidates should be valid and reversible."""
        proposer = ScriptedProposer()
        task_spec = {"objective": "test"}
        history = []

        for _ in range(5):
            candidate = proposer.propose(task_spec, history)
            assert candidate.type == "agent_config"
            assert isinstance(candidate.params, dict)
            assert "config_delta" in candidate.params
            assert candidate.reversible is True

    def test_proposed_deltas_never_include_forbidden_keys(self):
        """Proposer should never attempt to mutate frozen keys."""
        proposer = ScriptedProposer()
        task_spec = {"objective": "test"}
        history = []

        forbidden = {"_agent", "_grader", "_eval", "_loss_hash"}

        for _ in range(10):
            candidate = proposer.propose(task_spec, history)
            delta = candidate.params.get("config_delta", {})
            for key in delta:
                assert (
                    key not in forbidden
                ), f"Proposer tried to mutate frozen key '{key}'"


class TestProposerNeverLeaksHoldout:
    """Verify that proposers never receive or leak holdout data."""

    def test_scripted_proposer_does_not_access_holdout(self):
        """ScriptedProposer is deterministic and never accesses task_spec data."""
        proposer = ScriptedProposer()

        # Even if task_spec contains holdout, proposer doesn't look at it.
        task_spec = {
            "objective": "test",
            "train_examples": [{"input": "1+1", "expected": "2"}],
            "holdout_examples": [{"input": "2+2", "expected": "4"}],  # Should be ignored
        }
        history = []

        candidate = proposer.propose(task_spec, history)

        # The proposer should return a delta without ever examining the data.
        assert candidate.type == "agent_config"
        assert candidate.reversible is True

        # Verify it's just a config delta, not the data.
        delta = candidate.params.get("config_delta", {})
        for key in delta:
            assert (
                key not in task_spec
            ), "Proposer should not copy data keys into proposal"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
