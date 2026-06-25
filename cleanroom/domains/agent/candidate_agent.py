"""The MODIFIABLE SURFACE for agent self-improvement.

This module is the only file edited by the loop. Its source code is snapshotted,
modified by the proposer, and reloaded after each apply() - making the agent's
own behavior the optimization target.

The reference baseline is StationarityAgent: judge first, then escalate if
drift > THRESHOLD. This is intentionally a BAD starting point (THRESHOLD=0.95),
so the loop has room to bend down toward the optimum.

FROZEN DOCTRINE (#28):
  - The judge (bonds_instrument/judge.py) NEVER changes.
  - THRESHOLD is the ONLY tunable parameter in this module.
  - The loop will edit this file's source text (via importlib.reload) to propose
    changes. Any edit touching bonds_instrument/ or to this module's .review()
    contract is ESCALATED by the pore.
"""

from dataclasses import dataclass
from bonds_instrument import judge


# TUNABLE: This is the ONLY module-level constant that the loop edits.
# Default = 0.95 (high false-clear risk, good baseline for descent).
THRESHOLD = 0.95


@dataclass
class Decision:
    """Agent's verdict on a single claim."""
    verdict: str          # "ok" | "error" | "escalate"
    confidence: float = 1.0
    rationale: str = ""


class CandidateAgent:
    """A frozen-judge agent that escalates if drift exceeds THRESHOLD.

    This is the modifiable candidate being optimized by the loop. Its
    .review() method must remain stable; only THRESHOLD can be tuned.
    """

    def __init__(self):
        self.threshold = THRESHOLD
        self.name = f"candidate@{THRESHOLD}"

    def review(self, view: dict) -> Decision:
        """Judge first, then escalate on high drift.

        Args:
            view: Agent-visible claim dict with "drift" and other fields.

        Returns:
            Decision with verdict in {"ok", "error", "escalate"}.
        """
        # Gate 1: Does the arithmetic reconcile?
        if not judge.passes(view):
            return Decision("error", 1.0, "arithmetic does not reconcile")

        # Gate 2: Is the claim within the trusted region?
        if view.get("drift", 0.0) > self.threshold:
            return Decision(
                "escalate",
                1.0,
                f"drift>{self.threshold}: outside trusted region"
            )

        # Pass: Both gates satisfied.
        return Decision("ok", 1.0, "reconciles and within trusted region")
