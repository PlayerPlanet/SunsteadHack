"""Build re-derivable claims from the real data, then manufacture ground truth
by injecting known errors (contamination-proof: minted at runtime).

A Claim is one checkable (isin, field, value) unit. We keep only claims the judge
PASSES on the original data (the 'clean' pool), then poison a fraction with a known
corruption. The corruption catalog splits into:

  * judge-catchable  -> breaks the arithmetic; the re-derivable judge catches it.
  * judge-uncatchable -> leaves arithmetic intact but the value is semantically
                         wrong (wrong unit). Only reasoning/world-knowledge catches
                         it. We bias these toward HIGH drift (weirder bonds carry
                         more semantic/unit ambiguity), so the dumb region recedes.
"""

import random
from dataclasses import dataclass, field

from . import judge
from .data import drift_by_isin, drift_score, load_tables, num

CATCHABLE = {"decimal_shift", "recon_break", "coverage_break"}
UNCATCHABLE = {"unit_swap"}


@dataclass
class Claim:
    claim_id: str
    isin: str
    kind: str
    view: dict                       # agent-visible primitives ONLY
    drift: float
    truth: str = "clean"             # hidden: "clean" | "error"
    corruption: str | None = None    # hidden: which injection (if any)

    @property
    def judge_catchable(self) -> bool:
        return self.corruption in CATCHABLE


def build_clean_claims() -> list[Claim]:
    """All re-derivable claims the judge passes on the untouched data."""
    t = load_tables()
    dmap = drift_by_isin()
    claims: list[Claim] = []

    # per_million claims (one per impact row with the needed numbers)
    for i, r in enumerate(t["impacts"]):
        iv, pmu, bond = num(r["impact_value"]), num(r["impact_per_million_USD"]), num(r["bond_USD_amount"])
        if None in (iv, pmu, bond) or bond == 0:
            continue
        view = {"kind": "per_million", "impact_value": iv, "impact_per_million_USD": pmu,
                "bond_USD_amount": bond, "impact_unit": r.get("impact_unit", ""),
                "impact_metric": r.get("impact_metric", ""), "source_trail": r.get("source_trail", "")[:400],
                "drift": dmap.get(r["isin"], 0.5)}
        c = Claim(f"pmu:{i}", r["isin"], "per_million", view, view["drift"])
        if judge.passes(view):
            claims.append(c)

    # coverage + alloc_recon claims (from issuances)
    for i, r in enumerate(t["issuances"]):
        bond, alloc, unalloc = num(r["bond_USD_amount"]), num(r["total_USD_allocated"]), num(r["total_USD_unallocated"])
        cov = num(r["allocation_coverage_pct"])
        d = drift_score(r)
        if None not in (bond, alloc, cov) and bond:
            view = {"kind": "coverage", "bond_USD_amount": bond, "total_USD_allocated": alloc,
                    "allocation_coverage_pct": cov, "source_trail": (r.get("allocation_source_trail") or "")[:400], "drift": d}
            c = Claim(f"cov:{i}", r["isin"], "coverage", view, d)
            if judge.passes(view):
                claims.append(c)
        if None not in (bond, alloc, unalloc) and bond:
            view = {"kind": "alloc_recon", "bond_USD_amount": bond, "total_USD_allocated": alloc,
                    "total_USD_unallocated": unalloc, "drift": d}
            c = Claim(f"rec:{i}", r["isin"], "alloc_recon", view, d)
            if judge.passes(view):
                claims.append(c)

    _rank_normalize_drift(claims)
    return claims


def _rank_normalize_drift(claims: list[Claim]) -> None:
    """Map raw drift -> its percentile within the corpus, so 'drift' spreads across
    the full [0,1] axis. The raw structural score is compressed (features rarely hit
    extremes together); the percentile keeps the ORDER (which bond is weirder) while
    giving a readable, fully-populated axis. Mutates claims in place.
    """
    order = sorted(range(len(claims)), key=lambda i: claims[i].drift)
    denom = max(1, len(claims) - 1)
    for rank, i in enumerate(order):
        pct = round(rank / denom, 4)
        claims[i].drift = pct
        claims[i].view["drift"] = pct


# A provenance marker mirroring the REAL data's unverifiable rows (blank source_trails,
# review_notes like "provides no derivation"). The figure may be plausible, but with no
# checkable derivation an autonomous agent in a financial pipeline must DEFER to a human.
# Stated policy: unverifiable provenance => correct action is ESCALATE (truth=needs_human).
_UNVERIFIED_TRAIL = ("Source: unverified | no allocation/impact report located | figure is an "
                     "approximate estimate, not reconciled to any primary document")


def poison(claims: list[Claim], *, error_rate: float = 0.40, ambiguous_rate: float = 0.15,
           seed: int = 7) -> list[Claim]:
    """Build the labeled stream: clean + hard errors + genuinely-ambiguous (needs-human).

    Returns a NEW stream (the clean pool is never mutated). Ambiguous claims only apply
    where there is provenance to strip (per_million), grounded in the real data's
    unverifiable rows — there, the only correct action is to escalate.
    """
    rng = random.Random(seed)
    out: list[Claim] = []
    for c in claims:
        r = rng.random()
        make_ambiguous = r < ambiguous_rate and c.kind == "per_million"
        make_error = (not make_ambiguous) and r < ambiguous_rate + error_rate

        if make_ambiguous:
            v = dict(c.view)
            v["source_trail"] = _UNVERIFIED_TRAIL  # arithmetic still reconciles; provenance is gone
            out.append(Claim(c.claim_id, c.isin, c.kind, v, c.drift,
                             truth="needs_human", corruption="unverifiable"))
            continue
        if not make_error:
            out.append(c)  # stays clean
            continue

        v = dict(c.view)  # copy so we don't mutate the clean pool
        kind = c.kind
        # weirder bonds -> more semantic/unit ambiguity (uncatchable concentrates high).
        # drift**2 keeps low-drift bonds genuinely clean, so a real trustworthy region
        # exists at the bottom and recedes as drift rises.
        go_uncatchable = kind == "per_million" and rng.random() < c.drift ** 2
        # Catchable corruptions perturb the CLAIMED value past the judge's tolerance, so
        # the arithmetic always catches them (false-clears then come ONLY from unit_swap).
        if go_uncatchable:
            v["impact_unit"] = "ktCO2e" if "kt" not in v.get("impact_unit", "").lower() else "tCO2e"
            corruption = "unit_swap"                       # arithmetic reconciles; meaning is 1000x off
        elif kind == "per_million":
            v["impact_per_million_USD"] = v["impact_per_million_USD"] * 10.0   # claimed pmu off by 10x
            corruption = "decimal_shift"
        elif kind == "coverage":
            v["allocation_coverage_pct"] = v["allocation_coverage_pct"] + 5.0  # claimed coverage off by 5pp
            corruption = "coverage_break"
        else:  # alloc_recon — push the sum 5% of bond past the identity
            v["total_USD_unallocated"] = v["total_USD_unallocated"] + 0.05 * v["bond_USD_amount"]
            corruption = "recon_break"
        out.append(Claim(c.claim_id, c.isin, c.kind, v, c.drift, truth="error", corruption=corruption))
    return out
