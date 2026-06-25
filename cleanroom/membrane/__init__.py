"""The learned membrane — a SHADOW gate with an abstain head (issue #20).

WHAT THIS IS
------------
The frozen pore (`cleanroom/pore`) is a dumb rule: irreversible / high-blast /
claim-surface -> escalate. The deep probe (`cleanroom/probe`) showed that of the
escalations the pore raises, a human approves ~half of them — that "false-stop"
slack is the headroom the manifesto's amortized *membrane* would reclaim by
predicting the human's verdict and auto-clearing the calls it can stand behind.

This module is the smallest honest step toward that membrane: it learns the
human's approve/reject verdict from the probe's labels and exposes a THREE-outcome
gate (not two):

    auto_clear  — predicts the human would APPROVE; the pore's stop was a false stop.
    escalate    — predicts the human would REJECT; agrees with the pore.
    abstain     — not confident enough -> ask a human anyway.

The abstain head is the whole point: a calibrated agent that "knows its own edge"
must be allowed to say "I don't know" rather than being forced to guess. Point
classification (approve/reject) is not enough.

WHY IT IS SHADOW-ONLY (load-bearing — see ShadowMembranePore)
-------------------------------------------------------------
The membrane NEVER gets the wheel. `ShadowMembranePore` wraps the frozen pore
exactly like `cleanroom/pore/stationarity.py::StationarityProxyPore`: the frozen
pore still makes the real decision `run_loop` acts on; the wrapper additionally
records what the membrane *would* have decided. The bend it produces is therefore
*measured against* the frozen ruler, never produced by moving it. The frozen pore
stays byte-for-byte unchanged (tests/test_membrane.py asserts the file hash).

ASYMMETRIC ERROR COST (the calibration target)
----------------------------------------------
A FALSE-CLEAR (membrane auto-clears something the human would reject) is the
dangerous error — the agent acted past its edge. A retained false-stop is merely
the status quo (no worse than the frozen pore). So the membrane is tuned to
MINIMIZE false-clears even at the cost of abstaining more. It auto-clears a lever
only with a clean approve track record and zero rejects; any reject in a lever's
history (or an irreversible candidate) forces abstain/escalate. Erring toward
asking *is* the target — that is the difference between "knows its limits" and
"is often right".

WHAT THE DATA FORCED (read before changing the protocol)
--------------------------------------------------------
In the probe's 15 escalations the only feature that separates approve from reject
is the *lever identity*: every escalation is `reversible=True` and sits at
drift ~= 0.9, so `reversible` and `drift` are degenerate and carry no signal. The
honest consequence: the verdict is NOT predictable for a lever with no precedent.
Confronted with a genuinely novel lever the membrane therefore ABSTAINS — it
refuses to claim slack it cannot back. That is why the held-out protocol is
leave-one-lever-out (see scripts/eval_membrane.py), not held-out-regime: the
frozen pore concentrates 100% of escalations in the `regime_break` tier (the only
tier whose option menu offers systemic levers), so a held-out-regime split has
zero training labels and is infeasible. Leave-one-lever-out is the honest — and
stricter — analogue.

FROZEN-BASE DISCIPLINE
----------------------
This module never imports-and-mutates the base pore; it only *reads* its decision
through the wrapper. The base gate must stay drift-blind and untuned so the
boundary instrument (#4/#16) can still tell "the world drifted" from "the gate
moved". The membrane is the deferred Stage-2 bet measured against that fixed ruler
— it is not a substitute for it, and giving it the wheel is explicitly out of scope.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from cleanroom.types import Candidate

# Confidence band for the calibrated approve-probability (Laplace-smoothed per-lever
# approve fraction). Constants, not learned per-run. auto_clear requires p >= HIGH
# AND a clean record (zero rejects); escalate fires at p <= LOW or a reject-majority;
# the band in between is the abstain head. HIGH is 0.70 so a clean 2/0 lever (p=0.75
# under alpha=1) clears while the mixed 4/1 lever (p=0.71, but rj>0) is held back to
# abstain — exactly the asymmetric, false-clear-minimizing target.
ABSTAIN_LOW = 0.35
ABSTAIN_HIGH = 0.70

# Minimum number of labelled precedents a lever needs before the membrane will
# auto_clear on it. Below this it abstains even on a clean record — thin evidence
# is not standing-behind-it.
MIN_SUPPORT = 2

# Laplace smoothing for the calibrated approve-probability. alpha=1 keeps a pure
# 2/0 lever off 100% (-> 0.75), leaving honest calibration headroom on n~=15.
ALPHA = 1.0


def lever_of(candidate: Candidate) -> str:
    """The lever a candidate pulls — the key the verdict is separable on.

    GUC name if present, else an explicit op (e.g. VACUUM FULL), else the candidate
    type. Mirrors `scripts/fit_membrane.py::_lever` so the fit and the live gate key
    identically.
    """
    params = candidate.params or {}
    return params.get("name") or params.get("op") or candidate.type


@dataclass(frozen=True)
class MembraneDecision:
    """What the membrane *would* decide for one candidate (shadow only).

    Fields:
        decision: "auto_clear" | "escalate" | "abstain".
        p_approve: calibrated probability the human would APPROVE (Laplace-smoothed
            per-lever approve fraction). The reliability/ECE score, not just a label.
        lever: the lever the decision keyed on.
        seen: whether this lever had any precedent in the fit (False -> abstain).
        support: number of labelled precedents for this lever.
        reason: short, auditable explanation of which rule fired.
    """

    decision: str
    p_approve: float
    lever: str
    seen: bool
    support: int
    reason: str


@dataclass
class Membrane:
    """A transparent, precedent-based membrane fit on the probe's escalation labels.

    The "fit" is per-lever approve/reject counts. `evaluate` returns a 3-outcome
    `MembraneDecision` with a calibrated approve-probability and an abstain head.
    No ML dependency — the point is to show the slack is learnable and the residual
    is the irreducible lever, not to ship a model on 15 rows.

    Build it from the probe dataset (`Membrane.from_dataset`) or from explicit
    counts (`Membrane.from_counts`, used by unit tests and leave-one-lever-out).
    """

    lever_stats: dict  # lever -> {"approve": int, "reject": int}
    alpha: float = ALPHA
    min_support: int = MIN_SUPPORT
    abstain_low: float = ABSTAIN_LOW
    abstain_high: float = ABSTAIN_HIGH
    levers: tuple = field(default_factory=tuple)

    def __post_init__(self):
        self.levers = tuple(sorted(self.lever_stats))

    # --- constructors -------------------------------------------------------

    @classmethod
    def from_counts(cls, counts: dict, **kw) -> "Membrane":
        """Build from explicit {lever: {"approve": n, "reject": n}} counts."""
        clean = {
            lv: {"approve": int(c.get("approve", 0)), "reject": int(c.get("reject", 0))}
            for lv, c in counts.items()
        }
        return cls(lever_stats=clean, **kw)

    @classmethod
    def from_records(cls, records: list, *, exclude_lever: str | None = None, **kw) -> "Membrane":
        """Build from probe rows (dicts). Counts approve/reject per lever over the
        escalations that carry a human verdict. `exclude_lever` drops one lever's
        precedent entirely — the mechanism behind leave-one-lever-out.
        """
        counts: dict = defaultdict(lambda: {"approve": 0, "reject": 0})
        for r in records:
            if not r.get("escalated") or r.get("human_decision") not in ("approve", "reject"):
                continue
            cand = r["candidate"]
            lv = (cand.get("params") or {}).get("name") or (cand.get("params") or {}).get("op") or cand.get("type")
            if exclude_lever is not None and lv == exclude_lever:
                continue
            counts[lv][r["human_decision"]] += 1
        return cls.from_counts(counts, **kw)

    @classmethod
    def from_dataset(cls, path: str | Path = "artifacts/deep_probe/dataset.jsonl", **kw) -> "Membrane":
        """Build from a probe dataset.jsonl on disk."""
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls.from_records(rows, **kw)

    # --- the gate -----------------------------------------------------------

    def p_approve(self, lever: str) -> float | None:
        """Laplace-smoothed P(human approves | lever). None for an unseen lever."""
        stats = self.lever_stats.get(lever)
        if stats is None:
            return None
        a, rj = stats["approve"], stats["reject"]
        return (a + self.alpha) / (a + rj + 2 * self.alpha)

    def evaluate(self, candidate: Candidate, context: dict | None = None) -> MembraneDecision:
        """Shadow-decide one candidate. NEVER acts — returns what it *would* decide.

        Precedent-based, asymmetric toward abstaining (minimize false-clears):

          * unseen lever                      -> abstain  (no basis to stand behind)
          * irreversible candidate            -> abstain  (defense in depth)
          * clean approve record (0 rejects,
            support >= min_support)           -> auto_clear
          * any reject and reject-majority    -> escalate  (agrees with the pore)
          * mixed verdict / thin support      -> abstain  (the irreducible judgment)

        `context` may carry {"drift": float}; it is recorded but — by the data's own
        verdict (drift is degenerate across escalations) — not used to override the
        precedent rule. Kept in the signature so a future, richer fit can use it.
        """
        lever = lever_of(candidate)
        stats = self.lever_stats.get(lever)

        # Unseen lever: no precedent -> the abstain head fires. This is the honest
        # generalization behavior the data forces (see module docstring).
        if stats is None:
            return MembraneDecision(
                decision="abstain", p_approve=0.5, lever=lever, seen=False,
                support=0, reason="unseen-lever",
            )

        # Defense in depth: never auto_clear something irreversible, whatever the
        # record. (No escalation in the current data is irreversible, but the
        # membrane must never be the reason an irreversible change goes through.)
        if not candidate.reversible:
            return MembraneDecision(
                decision="abstain", p_approve=self.p_approve(lever), lever=lever,
                seen=True, support=stats["approve"] + stats["reject"],
                reason="irreversible-defense-in-depth",
            )

        a, rj = stats["approve"], stats["reject"]
        n = a + rj
        p = (a + self.alpha) / (n + 2 * self.alpha)

        # Clean approve precedent -> reclaim the false stop.
        if rj == 0 and n >= self.min_support and p >= self.abstain_high:
            return MembraneDecision(
                decision="auto_clear", p_approve=p, lever=lever, seen=True,
                support=n, reason=f"clean-approve-precedent({a}/0)",
            )

        # Reject-leaning -> agree with the pore and escalate.
        if rj > a or (rj > 0 and a == 0) or p <= self.abstain_low:
            return MembraneDecision(
                decision="escalate", p_approve=p, lever=lever, seen=True,
                support=n, reason=f"reject-precedent({a}/{rj})",
            )

        # Mixed verdict or thin support -> the irreducible judgment: abstain.
        return MembraneDecision(
            decision="abstain", p_approve=p, lever=lever, seen=True,
            support=n, reason=f"mixed-or-thin({a}/{rj})",
        )


# ----------------------------------------------------------------------------
# Shadow wiring — the membrane is measured, never given the wheel.
# ----------------------------------------------------------------------------

from cleanroom import pore as _base_pore  # noqa: E402  (after Membrane for readability)
from cleanroom.types import PoreResult  # noqa: E402


class ShadowMembranePore:
    """Frozen base pore + a shadow membrane tap, composed like StationarityProxyPore.

    `evaluate(candidate)` returns the BASE pore's decision unchanged — that is the
    decision `run_loop` acts on. Alongside, it records what the membrane *would*
    have decided into `self.shadow_log` (one entry per call). No live action is ever
    taken on the membrane's say-so; the frozen base pore is never edited.

    One sweep run is one drift level, so drift is bound at construction (the base
    `evaluate(candidate)` seam takes only the candidate), matching StationarityProxyPore.

    Args:
        membrane: a fitted `Membrane`.
        drift_level: the drift for this run, recorded into the membrane context.
        base: the base pore module/object (defaults to the frozen cleanroom.pore).
    """

    def __init__(self, *, membrane: Membrane, drift_level: float = 0.0, base=_base_pore):
        self.membrane = membrane
        self.drift_level = float(drift_level)
        self._base = base
        self.shadow_log: list[dict] = []

    def evaluate(self, candidate: Candidate) -> PoreResult:
        # The REAL decision — what run_loop acts on. Always the frozen base pore.
        base_result = self._base.evaluate(candidate)

        # Shadow tap: what the membrane WOULD decide. Recorded, never acted on.
        md = self.membrane.evaluate(candidate, {"drift": self.drift_level})
        self.shadow_log.append(
            {
                "lever": md.lever,
                "drift": self.drift_level,
                "base_decision": base_result.decision,
                "base_pore": base_result.pore,
                "base_escalated": base_result.requires_human_judgment,
                "membrane_decision": md.decision,
                "p_approve": md.p_approve,
                "membrane_reason": md.reason,
                "reversible": candidate.reversible,
            }
        )
        return base_result
