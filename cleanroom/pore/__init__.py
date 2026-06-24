"""Proof-of-Risk Evaluation (pore) — rule-based risk gating.

Frozen, dumb, rule-based. Gates blast-radius + reversibility — a PROXY for
'what the agent can stand behind', NOT the true epistemic edge. Must NOT
self-tune (issue #4's boundary benchmark depends on a frozen pore).

Story B (GitHub issue #3) owns the production pore ruleset and evaluation.
"""

from cleanroom.types import Candidate, PoreResult


def evaluate(candidate: Candidate) -> PoreResult:
    """Evaluate risk for a candidate.

    Args:
        candidate: The candidate to assess.

    Returns:
        A PoreResult indicating risk level, human judgment requirement, and decision.

    Raises:
        NotImplementedError: Story B owns this implementation.
    """
    raise NotImplementedError("evaluate — owned by Story B, GitHub issue #3")
