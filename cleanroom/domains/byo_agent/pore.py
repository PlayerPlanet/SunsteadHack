"""BYO-Agent pore (proof-of-risk-evaluation) — governance gate for config changes.

Routes config deltas into risk categories:
  - Low: system_prompt/few_shot/decoding params (safe, reversible)
  - Medium: model change (cost + behavior shift)
  - High: any attempt to mutate grader/eval/loss (frozen contract violation)
"""

from cleanroom.types import Candidate, PoreResult


class BYOAgentPore:
    """Evaluates the risk of a config change."""

    def evaluate(self, candidate: Candidate) -> PoreResult:
        """Assess risk and return decision.

        Args:
            candidate: Proposed candidate.

        Returns:
            PoreResult with risk_level and decision.
        """
        if candidate.type != "agent_config":
            return PoreResult(
                pore="agent_config_type",
                risk_level="high",
                requires_human_judgment=True,
                decision="block",
            )

        config_delta = candidate.params.get("config_delta", {})

        # Check for forbidden mutations.
        forbidden = {"_agent", "_grader", "_eval", "_loss_hash", "_logclient"}
        if any(key in config_delta for key in forbidden):
            return PoreResult(
                pore="agent_frozen_contract",
                risk_level="high",
                requires_human_judgment=True,
                decision="block",
            )

        # Check for model changes (medium risk: cost and behavior shift).
        if "model" in config_delta:
            return PoreResult(
                pore="agent_model_change",
                risk_level="medium",
                requires_human_judgment=True,
                decision="escalate",
            )

        # All other changes (system_prompt, few_shot, temperature, etc.) are low-risk.
        return PoreResult(
            pore="agent_low_risk",
            risk_level="low",
            requires_human_judgment=False,
            decision="allow",
        )
