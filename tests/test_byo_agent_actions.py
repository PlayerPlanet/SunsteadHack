"""Tests for BYO-Agent actions — verify apply/rollback round-trip."""

import pytest

from cleanroom.domains.byo_agent.actions import BYOAgentActions
from cleanroom.types import Candidate


class TestBYOAgentActions:
    """Test action apply and rollback."""

    def test_apply_then_rollback_round_trip(self):
        """apply() then rollback() should restore exact prior config."""
        actions = BYOAgentActions()

        env = {
            "_cur_config": {
                "system_prompt": "original",
                "temperature": 1.0,
                "max_tokens": 100,
            },
            "_config_stack": [],
        }

        # Apply a delta.
        candidate = Candidate(
            type="agent_config",
            params={
                "config_delta": {
                    "system_prompt": "modified",
                    "temperature": 0.5,
                }
            },
            reversible=True,
        )

        actions.apply(env, candidate)

        # Config should be updated.
        assert env["_cur_config"]["system_prompt"] == "modified"
        assert env["_cur_config"]["temperature"] == 0.5
        assert env["_cur_config"]["max_tokens"] == 100  # Unchanged

        # Stack should have the prior config.
        assert len(env["_config_stack"]) == 1
        assert env["_config_stack"][0]["system_prompt"] == "original"
        assert env["_config_stack"][0]["temperature"] == 1.0

        # Rollback.
        actions.rollback(env, candidate)

        # Config should be restored exactly.
        assert env["_cur_config"]["system_prompt"] == "original"
        assert env["_cur_config"]["temperature"] == 1.0
        assert env["_cur_config"]["max_tokens"] == 100

        # Stack should be empty again.
        assert len(env["_config_stack"]) == 0

    def test_multiple_apply_rollback(self):
        """Multiple apply/rollback pairs should work correctly."""
        actions = BYOAgentActions()

        env = {
            "_cur_config": {"temp": 1.0},
            "_config_stack": [],
        }

        # First apply.
        candidate1 = Candidate(
            type="agent_config",
            params={"config_delta": {"temp": 2.0}},
            reversible=True,
        )
        actions.apply(env, candidate1)
        assert env["_cur_config"]["temp"] == 2.0

        # Second apply.
        candidate2 = Candidate(
            type="agent_config",
            params={"config_delta": {"temp": 3.0}},
            reversible=True,
        )
        actions.apply(env, candidate2)
        assert env["_cur_config"]["temp"] == 3.0

        # Stack should have both prior configs.
        assert len(env["_config_stack"]) == 2

        # First rollback.
        actions.rollback(env, candidate2)
        assert env["_cur_config"]["temp"] == 2.0

        # Second rollback.
        actions.rollback(env, candidate1)
        assert env["_cur_config"]["temp"] == 1.0

    def test_apply_rejects_non_agent_config(self):
        """apply() should reject candidates with wrong type."""
        actions = BYOAgentActions()
        env = {"_cur_config": {}, "_config_stack": []}

        bad_candidate = Candidate(
            type="index", params={"config_delta": {}}, reversible=True
        )

        with pytest.raises(ValueError, match="expected type='agent_config'"):
            actions.apply(env, bad_candidate)

    def test_empty_delta_is_noop_but_pushes_stack(self):
        """apply() with an empty delta should be a no-op but still push the stack."""
        actions = BYOAgentActions()

        env = {
            "_cur_config": {"temp": 1.0},
            "_config_stack": [],
        }

        candidate = Candidate(
            type="agent_config",
            params={"config_delta": {}},  # Empty delta
            reversible=True,
        )

        actions.apply(env, candidate)

        # Config unchanged.
        assert env["_cur_config"]["temp"] == 1.0

        # Stack should still be pushed.
        assert len(env["_config_stack"]) == 1
        assert env["_config_stack"][0]["temp"] == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
