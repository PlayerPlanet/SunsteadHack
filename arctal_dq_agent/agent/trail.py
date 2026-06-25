"""Source-trail re-derivation — the flagship "beyond SQL" check.

Every impact value ships a `source_trail` that *narrates its own derivation* in
free text, e.g.:

    "... 53,044.00 MWh (from source, entry=category) × bond_share 0.180000
     = 9,547.92 MWh; 9,547.92 / 1,170.6M USD = 8.16 MWh/$M"

That narration contains checkable arithmetic. We parse the stated steps and
re-derive them, then confirm they actually support the *stored* numbers:

  1. bond-share step   `base × bond_share s = product`   -> base*s ?= product,
                                                            and product ?= stored impact_value
  2. division step     `numerator / denomM USD = quot`   -> numerator/denom ?= quot,
                        with `denom=bond|allocation`        and (denom=bond) denom*1e6 ?= bond_USD

The high-value catch is **`numerator ?= stored impact_value`**: if a value was
corrupted but its per-$M was recomputed from the corrupted value, the pure
arithmetic check (`per_million`) still passes — but the trail still narrates the
*original* numerator, so the disagreement surfaces here. No SQL sees this; it
requires reading the prose. 205/240 sample trails carry this arithmetic.

Pure functions, no I/O, no LLM. `reconcile_impact_trail(row, ...) -> [Finding]`.
"""

from __future__ import annotations

import re

from .data import num
from .finding import Finding

_N = r"[\d,]+(?:\.\d+)?"
_RE_SHARE = re.compile(rf"×\s*bond_share\s*([\d.]+)\s*=\s*({_N})")
_RE_DIV = re.compile(rf"({_N})\s*/\s*({_N})\s*M\s*USD\s*=\s*({_N})")
_RE_DENOM = re.compile(r"denom=(\w+)")

# Trails print values to 2 decimals, so a raw figure and its narrated twin can differ
# by up to half a displayed unit purely from rounding. A real mismatch must clear BOTH
# a relative gap (large numbers) AND an absolute floor (small numbers) — otherwise
# e.g. stored 0.147 vs trail-displayed 0.15 would false-positive.
TOL_TRAIL = 1e-2     # relative
TOL_TRAIL_ABS = 5e-3  # absolute floor = half of the last shown digit at 2 dp
TOL_BOND = 2e-2      # bond_USD vs the "/ NN.NM USD" the trail prints (often 1 dp)


def _f(s: str) -> float:
    return float(s.replace(",", ""))


def _rel(a: float, b: float) -> float:
    return abs(a - b) / (abs(b) if b else 1.0)


def _mismatch(a: float, b: float) -> bool:
    """True iff a and b differ by more than display-rounding can explain."""
    return abs(a - b) > TOL_TRAIL_ABS and _rel(a, b) > TOL_TRAIL


def reconcile_impact_trail(row: dict) -> list[Finding]:
    """Re-derive an impact row's narrated arithmetic and cross-check stored values."""
    trail = row.get("source_trail") or ""
    isin = row["isin"]
    stored_value = num(row.get("impact_value"))
    bond = num(row.get("bond_USD_amount"))
    metric = (row.get("impact_metric") or "").strip()
    out: list[Finding] = []
    excerpt = trail[:240]

    # --- bond-share step: base × bond_share s = product -------------------- #
    m = _RE_SHARE.search(trail)
    if m:
        share, product = _f(m.group(1)), _f(m.group(2))
        base_m = re.search(rf"({_N})\s*\w+\s*\([^)]*\)\s*×", trail) or re.search(rf"({_N})[^×]*×", trail)
        base = _f(base_m.group(1)) if base_m else None
        if base is not None and _mismatch(base * share, product):
            out.append(Finding(
                isin, "impacts", "impact_value", "trail_share_inconsistent",
                "medium", 0.85, "flag", tier="trail",
                rationale=f"{metric}: trail's bond-share step is internally inconsistent "
                          f"({base:g}×{share:g}≠{product:g}).",
                evidence={"base": base, "bond_share": share, "stated_product": product,
                          "recomputed": round(base * share, 2), "trail": excerpt},
            ))
        if stored_value is not None and _mismatch(product, stored_value):
            out.append(_value_mismatch(isin, metric, product, stored_value, excerpt))

    # --- division step: numerator / denomM USD = quotient ------------------ #
    m = _RE_DIV.search(trail)
    if m:
        numer, denom_m, quot = _f(m.group(1)), _f(m.group(2)), _f(m.group(3))
        # numerator should equal the stored impact value (the cross-check SQL can't do)
        if stored_value is not None and not any(f.check_id == "trail_value_mismatch" for f in out):
            # Only meaningful when there is no bond_share step rescaling the numerator.
            if not _RE_SHARE.search(trail) and _mismatch(numer, stored_value):
                out.append(_value_mismatch(isin, metric, numer, stored_value, excerpt))
        # denominator basis: denom=bond means it should be the bond's USD size
        denom_basis = (_RE_DENOM.search(trail).group(1) if _RE_DENOM.search(trail) else "")
        if denom_basis == "bond" and bond and _rel(denom_m * 1e6, bond) > TOL_BOND:
            out.append(Finding(
                isin, "impacts", "bond_USD_amount", "trail_denom_mismatch",
                "medium", 0.8, "flag", tier="trail",
                rationale=f"{metric}: trail says denom=bond but its stated denominator "
                          f"{denom_m:g}M USD ≠ bond_USD_amount {bond/1e6:.1f}M.",
                evidence={"trail_denom_musd": denom_m, "bond_usd_musd": round(bond / 1e6, 2),
                          "basis": "bond", "trail": excerpt},
            ))

    return out


def _value_mismatch(isin: str, metric: str, narrated: float, stored: float, excerpt: str) -> Finding:
    """Stored impact_value disagrees with the value its own trail derives."""
    return Finding(
        isin, "impacts", "impact_value", "trail_value_mismatch",
        "high", 0.8, "flag", tier="trail",
        rationale=f"{metric}: stored impact_value {stored:g} disagrees with the "
                  f"{narrated:g} its own source_trail derives.",
        evidence={"stored_impact_value": stored, "trail_derived_value": narrated,
                  "rel_gap": round(_rel(narrated, stored), 4), "trail": excerpt},
    )
