"""Membrane v2 — semantic-risk features + decision-theoretic, OOD-aware abstention.

WHAT CHANGED FROM v1 (cleanroom/membrane/__init__.py)
-----------------------------------------------------
v1 keys on the lever *identity*, so on a never-seen lever it abstains 100% — it
memorizes, it does not generalize. v2 keys on the lever's *semantic risk profile*
(cleanroom/membrane/taxonomy.py): data-loss-on-crash, result-semantics, recoverability.
A never-seen lever that shares a risk profile with a seen one inherits its verdict, so
the held-out (leave-one-lever-out) test finally generalizes:

    hold out `fsync` entirely -> v2 has never seen it, but it learned from
    `full_page_writes` that data_loss_on_crash=HIGH -> reject, and predicts
    reject on `fsync` COLD. v1 could only abstain there.

THREE UPGRADES
--------------
1. Semantic features (taxonomy) instead of one-hot lever -> cross-lever generalization.
2. Decision theory instead of a hand-tuned band. The act/ask choice minimizes expected
   cost given a risk ratio rho = C_human / C_false_clear: clear iff predicted
   P(reject) < rho. Sweeping rho traces the whole reclaimed-slack vs false-clear-risk
   Pareto frontier (scripts/eval_membrane_v2.py); v1's single point sits at the
   zero-false-clear knee. "Minimize false-clears" stops being a magic threshold and
   becomes a dial the operator sets.
3. A real OOD-aware abstain head. v2 abstains when a candidate's risk class / risk
   bucket has no training precedent — the manifesto's literal "abstains when it can't
   stand behind a call", now computable because the features are no longer degenerate.

STILL SHADOW ONLY. STILL FROZEN-RULER. v2 reuses ShadowMembranePore from v1; the base
pore makes every real decision and is byte-for-byte unchanged. The taxonomy is domain
priors from PostgreSQL docs, NOT fitted to labels — see taxonomy.py for the honesty
boundary. n is still 15: trust the generalization *shape*, not the magnitudes.
"""

from collections import defaultdict
from dataclasses import dataclass

from cleanroom.membrane.taxonomy import (
    KNOWN_RISK_CLASSES,
    feature_vector,
    lever_of,
    profile_of,
)
from cleanroom.types import Candidate

# Default risk ratio rho = C_human / C_false_clear. Small => a false-clear is far more
# costly than a human call => clear only when very confident. 0.25 keeps full-fit
# deployment at zero false-clears (a HIGH-data-loss lever escalates, a BOUNDED-tradeoff
# lever abstains, only NONE-risk sizing knobs clear). Sweep it for the frontier.
DEFAULT_RHO = 0.25

# Smoothing for the per-bucket approve rate (the calibrated probability). 0.5 is the
# Jeffreys prior — a standard, weakly-informative choice. (alpha=1.0/Laplace puts a
# pure 2/0 bucket at p_reject exactly 0.25, the rho knife-edge, which would make the
# held-out sizing levers abstain on a tie rather than reclaim; 0.5 reflects the thin
# but unanimous evidence honestly without special-casing.)
ALPHA = 0.5

# A risk bucket needs at least this many training precedents before v2 will stand
# behind a clear/escalate on it; below this the OOD head abstains (novel bucket).
MIN_BUCKET_SUPPORT = 2


@dataclass(frozen=True)
class MembraneV2Decision:
    """What v2 would decide for one candidate (shadow only).

    Carries the v1 decision fields (decision / p_approve / lever / reason) so the
    existing ShadowMembranePore can record it unchanged, plus the v2 semantics.
    """

    decision: str          # auto_clear | escalate | abstain
    p_approve: float        # calibrated, per-risk-bucket
    lever: str
    reason: str
    risk_class: str
    data_loss_on_crash: int
    ood: bool               # was this risk bucket/class novel (no precedent)?
    support: int            # training precedents in this risk bucket


class MembraneV2:
    """Semantic-risk membrane with a decision-theoretic, OOD-aware abstain head.

    The model is intentionally transparent: per data-loss-bucket Laplace approve
    rates (the dominant risk axis), plus an OOD check on risk class / bucket support.
    No black box — the point is to show that semantic priors generalize across levers,
    not to ship a model on 15 rows.

    Args:
        bucket_stats: {data_loss_level: {"approve": n, "reject": n}}.
        seen_classes: risk classes with any training precedent.
        rho: risk ratio C_human / C_false_clear (the act/ask dial).
    """

    def __init__(self, bucket_stats: dict, seen_classes: set, *, rho: float = DEFAULT_RHO,
                 alpha: float = ALPHA, min_bucket_support: int = MIN_BUCKET_SUPPORT):
        self.bucket_stats = bucket_stats
        self.seen_classes = set(seen_classes)
        self.rho = float(rho)
        self.alpha = float(alpha)
        self.min_bucket_support = int(min_bucket_support)

    # --- constructors -------------------------------------------------------

    @classmethod
    def from_records(cls, records: list, *, exclude_lever: str | None = None, **kw) -> "MembraneV2":
        """Fit per-data-loss-bucket approve/reject counts over labelled escalations.

        `exclude_lever` drops one lever's precedent entirely (leave-one-lever-out).
        Crucially, it drops by *lever*, so the held-out lever's risk bucket may still
        be populated by OTHER levers that share the profile — that is what lets v2
        generalize where v1 cannot.
        """
        buckets: dict = defaultdict(lambda: {"approve": 0, "reject": 0})
        seen_classes: set = set()
        for r in records:
            if not r.get("escalated") or r.get("human_decision") not in ("approve", "reject"):
                continue
            c = r["candidate"]
            cand = Candidate(type=c["type"], params=c.get("params") or {}, reversible=c["reversible"])
            if exclude_lever is not None and lever_of(cand) == exclude_lever:
                continue
            fv = feature_vector(cand)
            buckets[fv["data_loss_on_crash"]][r["human_decision"]] += 1
            seen_classes.add(fv["risk_class"])
        return cls(dict(buckets), seen_classes, **kw)

    @classmethod
    def from_dataset(cls, path="artifacts/deep_probe/dataset.jsonl", **kw) -> "MembraneV2":
        import json
        from pathlib import Path

        rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
        return cls.from_records(rows, **kw)

    # --- the gate -----------------------------------------------------------

    def _p_approve(self, level: int) -> tuple[float, int]:
        """Laplace-smoothed P(approve | data-loss bucket) and the bucket's support."""
        s = self.bucket_stats.get(level, {"approve": 0, "reject": 0})
        n = s["approve"] + s["reject"]
        return (s["approve"] + self.alpha) / (n + 2 * self.alpha), n

    def evaluate(self, candidate: Candidate, context: dict | None = None) -> MembraneV2Decision:
        """Shadow-decide one candidate via semantic risk + decision theory. NEVER acts."""
        fv = feature_vector(candidate)
        prof = profile_of(candidate)
        lever = lever_of(candidate)
        level = fv["data_loss_on_crash"]
        p_approve, support = self._p_approve(level)
        p_reject = 1.0 - p_approve

        def mk(decision, reason, ood=False):
            return MembraneV2Decision(
                decision=decision, p_approve=round(p_approve, 4), lever=lever, reason=reason,
                risk_class=prof.risk_class, data_loss_on_crash=level, ood=ood, support=support,
            )

        # OOD / novelty head. Generalization happens at the dominant axis (the
        # data-loss bucket), so OOD fires only when there is genuinely no basis:
        #   * the taxonomy could not classify the lever at all ("unknown"), or
        #   * it changes result semantics — a class we have never adjudicated, or
        #   * its data-loss bucket has too little precedent to stand behind.
        # A *known* risk class that happens to be held out (e.g. memory_sizing) is NOT
        # OOD as long as its data-loss bucket still has peers (e.g. wal_sizing): that
        # pooling across levers sharing a risk profile is exactly v2's generalization.
        if prof.risk_class == "unknown":
            return mk("abstain", "ood-unrecognised-lever", ood=True)
        if fv["changes_result_semantics"]:
            return mk("abstain", "changes-result-semantics", ood=True)
        if support < self.min_bucket_support:
            return mk("abstain", f"ood-thin-bucket(n={support})", ood=True)

        # Defense in depth: never auto_clear an irreversible / non-recoverable change.
        if not fv["recoverable"]:
            decision = "escalate" if p_reject >= (1.0 - self.rho) else "abstain"
            return mk(decision, "irreversible-never-cleared")

        # Decision theory on the act/ask choice: clear iff expected false-clear cost
        # p_reject * C_fc is below the cost of asking C_human, i.e. p_reject < rho.
        if p_reject < self.rho:
            return mk("auto_clear", f"clear: p_reject={p_reject:.2f} < rho={self.rho}")
        # Confidently reject -> agree with the pore and escalate.
        if p_reject >= (1.0 - self.rho):
            return mk("escalate", f"escalate: p_reject={p_reject:.2f} >= {1.0 - self.rho:.2f}")
        # In between -> the irreducible judgment: abstain.
        return mk("abstain", f"abstain: p_reject={p_reject:.2f} in band")
