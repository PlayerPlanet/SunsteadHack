"""Proof-of-Risk Evaluation (pore) — rule-based risk gating.

Frozen, dumb, rule-based. Gates blast-radius + reversibility — a PROXY for
'what the agent can stand behind', NOT the true epistemic edge. Must NOT
self-tune (issue #4's boundary benchmark depends on a frozen pore).

Story B (GitHub issue #3) owns the production pore ruleset and evaluation.

================================ READ THIS ====================================
WHY THIS IS DELIBERATELY DUMB
------------------------------
This function is an `if`-statement, on purpose. The interesting judgment in the
system lives upstream in the proposer (deciding *what* to try). The pore's only job
is the boundary act of the thesis: "stop and ask a human when acting would be unsafe
to be *wrong* about."

It gates two observable, model-free properties:

    irreversible  OR  high-blast-radius  OR  touches a claim/clinical surface
        -> escalate (requires_human_judgment = True)

That is a LOWER BOUND on the true epistemic edge ("what the agent can actually stand
behind"), and we label it as a proxy everywhere. The calibrated, OOD-aware membrane
that would approximate the *true* edge is the deferred research bet (issue #4 / the
manifesto's "amortized judge") — it is NOT this function.

FROZEN. DO NOT add learning, thresholds-from-data, or per-run adaptation here. The
Level-2 boundary benchmark (issue #4) measures escalation-rate vs. drift against a
*fixed* pore; if the pore self-tuned you could no longer tell "the world drifted"
from "the gate moved", which re-introduces the runaway-threshold failure the whole
instrument exists to detect.
===============================================================================
"""

from cleanroom.types import Candidate, PoreResult

# GUC parameters whose change has wide/systemic blast radius even when technically
# "reversible". Restart-context params (Gate-1: shared_buffers, max_connections) bounce
# the service; the rest reshape global planner/memory behaviour for every session.
_HIGH_BLAST_RADIUS_GUCS = frozenset(
    {
        "shared_buffers",
        "max_connections",
        "wal_level",
        "max_wal_size",
        "fsync",
        "full_page_writes",
        "synchronous_commit",
    }
)


def _is_high_blast_radius(candidate: Candidate) -> bool:
    """True if applying this candidate has wide/systemic reach.

    Pure, frozen heuristics over candidate metadata only (the pore cannot inspect the
    live DB — that would make it stateful and unfreezable):
      - an explicit `blast_radius: "high"` marker in params, or
      - a GUC change to a known systemic parameter.
    """
    params = candidate.params or {}

    if str(params.get("blast_radius", "")).lower() == "high":
        return True

    if candidate.type == "guc":
        name = params.get("name")
        if name in _HIGH_BLAST_RADIUS_GUCS:
            return True

    return False


def _touches_claim_surface(candidate: Candidate) -> bool:
    """True if the candidate touches a clinical/claim surface requiring human sign-off.

    Carried as an explicit `touches_claim_surface: True` flag on the candidate params.
    Mirrors the membrane-probe's clinical-claim gate: anything that could make a
    user-facing factual/clinical claim is never auto-applied.
    """
    return bool((candidate.params or {}).get("touches_claim_surface", False))


def evaluate(candidate: Candidate) -> PoreResult:
    """Evaluate risk for a candidate (pure, frozen, rule-based).

    Escalates (requires_human_judgment=True, decision="escalate") when the candidate
    is irreversible, high-blast-radius, or touches a claim/clinical surface. Otherwise
    allows (requires_human_judgment=False, decision="allow").

    Args:
        candidate: The candidate to assess.

    Returns:
        PoreResult(pore, risk_level, requires_human_judgment, decision).
        `pore` names the rule that fired, for the escalation log / dashboard.
    """
    irreversible = not candidate.reversible
    high_blast = _is_high_blast_radius(candidate)
    claim_surface = _touches_claim_surface(candidate)

    if irreversible or high_blast or claim_surface:
        # Name the *first* triggering reason for a legible audit trail.
        if irreversible:
            pore = "reversibility"
        elif high_blast:
            pore = "blast_radius"
        else:
            pore = "claim_surface"

        return PoreResult(
            pore=pore,
            risk_level="high",
            requires_human_judgment=True,
            decision="escalate",
        )

    return PoreResult(
        pore="auto_safe",
        risk_level="low",
        requires_human_judgment=False,
        decision="allow",
    )
