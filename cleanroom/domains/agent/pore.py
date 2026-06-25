"""Agent pore (proof-of-risk-evaluation) — governance gate for source edits.

DESIGN (Issue #28 — honesty doctrine):
The judge (bonds_instrument/judge.py) and the loop's decision logic are FROZEN.
Only candidate_agent.py is modifiable. Any edit touching the judge or reaching
outside agent/ escalates.

Risk categories:
  - Low: In-scope edits to candidate_agent.py THRESHOLD value only.
  - High: Judge-touching, out-of-scope, or oversized edits -> ESCALATE.

The pore is TESTABLE: a judge-touching edit must escalate.
"""

from cleanroom.types import Candidate, PoreResult


class AgentPore:
    """Evaluates the risk and scope of source edits."""

    def evaluate(self, candidate: Candidate) -> PoreResult:
        """Assess risk and return decision.

        Args:
            candidate: Proposed candidate with type="source_edit" and params:
                - source_text (optional): Full new source code.
                - threshold (optional): New THRESHOLD value.

        Returns:
            PoreResult with risk_level and decision.
        """
        if candidate.type != "source_edit":
            return PoreResult(
                pore="agent_edit_type",
                risk_level="high",
                requires_human_judgment=True,
                decision="block",
            )

        # Extract the new source or threshold.
        source_text = candidate.params.get("source_text")
        threshold = candidate.params.get("threshold")

        if source_text is None and threshold is None:
            return PoreResult(
                pore="agent_edit_empty",
                risk_level="high",
                requires_human_judgment=True,
                decision="block",
            )

        # If source_text is provided, check for frozen-boundary violations.
        if source_text is not None:
            # FORBIDDEN: Touching judge or instrument.
            if (
                "bonds_instrument.judge" in source_text
                or "bonds_instrument.instrument" in source_text
                or "from bonds_instrument import judge" in source_text
                or "import bonds_instrument.judge" in source_text
                or "import bonds_instrument.instrument" in source_text
                or "def passes(" in source_text  # Likely trying to redefine judge.passes
            ):
                return PoreResult(
                    pore="agent_judge_frozen",
                    risk_level="high",
                    requires_human_judgment=True,
                    decision="escalate",
                )

            # FORBIDDEN: Attempting to edit files outside candidate_agent.py.
            # (A full source edit should only modify candidate_agent.py content,
            # not import or reference other domains.)
            if (
                "cleanroom/domains/" in source_text
                and "candidate_agent" not in source_text
            ):
                return PoreResult(
                    pore="agent_out_of_scope",
                    risk_level="high",
                    requires_human_judgment=True,
                    decision="escalate",
                )

            # FORBIDDEN: Oversized diffs (e.g., > ~40 changed lines).
            # Count newlines as a rough heuristic.
            line_count = source_text.count('\n')
            if line_count > 200:  # Reasonable upper bound for a single-module edit.
                return PoreResult(
                    pore="agent_oversized_edit",
                    risk_level="high",
                    requires_human_judgment=True,
                    decision="escalate",
                )

        # ALLOWED: threshold-only edit, in-scope, no boundary violations.
        if threshold is not None and source_text is None:
            # Sanity check: threshold should be in [0.0, 1.0].
            if not (0.0 <= threshold <= 1.0):
                return PoreResult(
                    pore="agent_threshold_invalid",
                    risk_level="high",
                    requires_human_judgment=True,
                    decision="block",
                )

        return PoreResult(
            pore="agent_low_risk",
            risk_level="low",
            requires_human_judgment=False,
            decision="allow",
        )
