"""Bond extraction pore (proof-of-risk-evaluation) — governance gate for config changes.

Routes config deltas into risk categories:
  - Low: Safe extractor tuning on objective fields (field patterns, validation config)
  - High: Any attempt to mutate grader/eval/loss, or tune interpretation fields
  - Block: Any high-risk or field-without-document-grounded-gold mutation
"""

from cleanroom.types import Candidate, PoreResult


class BondPore:
    """Evaluates the risk of an extractor config change."""

    def evaluate(self, candidate: Candidate, env: dict | None = None) -> PoreResult:
        """Assess risk and return decision.

        Args:
            candidate: Proposed candidate.
            env: Optional domain environment (used to check field validity).

        Returns:
            PoreResult with risk_level and decision.
        """
        if candidate.type != "extractor_config":
            return PoreResult(
                pore="extractor_config_type",
                risk_level="high",
                requires_human_judgment=True,
                decision="block",
            )

        config_delta = candidate.params.get("config_delta", {})

        # Check for forbidden mutations of frozen keys.
        forbidden = {
            "_extractor",
            "_grader",
            "_eval",
            "_loss_hash",
            "_logclient",
        }
        if any(key in config_delta for key in forbidden):
            return PoreResult(
                pore="bond_frozen_contract",
                risk_level="high",
                requires_human_judgment=True,
                decision="block",
            )

        # If env is provided, check if any fields targeted are interpretation fields.
        if env:
            interpretation_fields = set()
            interpretation_rows = env.get("_interpretation", [])
            for row in interpretation_rows:
                interpretation_fields.add(row.get("field_name", ""))

            # Check if field_patterns targets any interpretation field.
            field_patterns = config_delta.get("field_patterns", {})
            for field_name in field_patterns.keys():
                if field_name in interpretation_fields:
                    return PoreResult(
                        pore="bond_interpretation_field",
                        risk_level="high",
                        requires_human_judgment=True,
                        decision="escalate",
                    )

        # All other extractor config changes (patterns, validation flags) are low-risk.
        return PoreResult(
            pore="bond_low_risk",
            risk_level="low",
            requires_human_judgment=False,
            decision="allow",
        )
