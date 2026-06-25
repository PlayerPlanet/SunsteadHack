"""Tier 0 — deterministic checks (run on every row, ~free, scale to 30k).

These are the re-derivable arithmetic identities and cross-table consistencies.
They are necessary for trust and cheap enough to run on the whole corpus, but they
are NOT where the agent earns its keep — they are the triage filter that decides
which rows are worth a (paid) Tier-1 reasoning pass.

Each check is a pure function `(row, ctx) -> list[Finding]`. Where a value is
*objectively* recomputable (e.g. coverage % from allocated/bond), a clean break
is dispositioned `auto_correct` with the recomputed number; where the arithmetic
only proves inconsistency without telling us which side is wrong, it is `flag`.

check_id reference (also see each function's docstring):
  per_million        impact_per_million_USD == impact_value / (denom_USD/1e6)
  coverage           allocation_coverage_pct == 100*total_USD_allocated/bond_USD
  alloc_recon        total_USD_allocated + total_USD_unallocated == bond_USD
  cat_usd_sum        sum(post_allocation_USD over isin) == total_USD_allocated
  share_def          post_allocation_share_of_total == post_allocation_USD/bond_USD
  category_count     *_icma_categories_number == len(split(*_icma_categories,';'))
  fx_consensus       bond_USD/bond_amount within tol of per-currency median rate
  date_sanity        placement_date < maturity_date
  xtab_bond_usd      same ISIN's bond_USD_amount agrees across files
  duplicate_isin     ISIN appears in >1 issuance row (divergence at scale)
"""

from __future__ import annotations

import re

from .data import Context, num
from .finding import Finding
from .trail import reconcile_impact_trail

# Tolerances kept here so they are visible and tunable in one place.
TOL_REL = 1e-3        # generic relative tolerance for re-derived ratios
TOL_COVERAGE_PP = 0.1  # percentage points for coverage
TOL_RECON_REL = 1e-4   # allocated + unallocated == bond (tight; same units)
TOL_FX_REL = 5e-2      # implied FX vs per-currency consensus (rates drift over time)


def _rel(a: float, b: float) -> float:
    return abs(a - b) / (abs(b) if b else 1.0)


def _denom_basis(trail: str) -> str:
    m = re.search(r"denom=(\w+)", trail or "")
    return m.group(1) if m else ""


# --------------------------------------------------------------------------- #
# impacts                                                                      #
# --------------------------------------------------------------------------- #

def check_per_million(row: dict, ctx: Context) -> list[Finding]:
    """impact_per_million_USD must equal impact_value / (denom_USD / 1e6).

    The denominator basis is read from the trail (`denom=bond` vs `denom=allocation`).
    When denom=bond we hold the bond's USD size and can recompute the intensity
    exactly -> a clean break is auto-correctable.
    """
    value = num(row.get("impact_value"))
    pmu = num(row.get("impact_per_million_USD"))
    bond = num(row.get("bond_USD_amount"))
    if value is None or pmu is None:
        return []
    basis = _denom_basis(row.get("source_trail", ""))
    if basis != "bond" or not bond:
        return []  # allocation-denominated intensities need the allocation USD; skip here
    expected = value / (bond / 1e6)
    if _rel(pmu, expected) <= TOL_REL:
        return []
    return [Finding(
        row["isin"], "impacts", "impact_per_million_USD", "per_million",
        "high", 0.99, "auto_correct", tier="deterministic",
        rationale=f"{row.get('impact_metric','')}: per-$M intensity is off "
                  f"({pmu:.2f} stored vs {expected:.2f} recomputed from value÷bond).",
        evidence={"stored": pmu, "expected": round(expected, 4), "impact_value": value,
                  "bond_USD_amount": bond, "denom_basis": "bond"},
        proposed_correction=round(expected, 4),
    )]


# --------------------------------------------------------------------------- #
# issuances                                                                    #
# --------------------------------------------------------------------------- #

def check_coverage(row: dict, ctx: Context) -> list[Finding]:
    """allocation_coverage_pct == 100 * total_USD_allocated / bond_USD_amount."""
    bond = num(row.get("bond_USD_amount"))
    alloc = num(row.get("total_USD_allocated"))
    cov = num(row.get("allocation_coverage_pct"))
    if bond is None or alloc is None or cov is None or not bond:
        return []
    expected = 100.0 * alloc / bond
    if abs(cov - expected) <= TOL_COVERAGE_PP:
        return []
    return [Finding(
        row["isin"], "issuances", "allocation_coverage_pct", "coverage",
        "medium", 0.99, "auto_correct", tier="deterministic",
        rationale=f"Coverage % disagrees with allocated÷bond "
                  f"({cov:.2f}% stored vs {expected:.2f}% recomputed).",
        evidence={"stored": cov, "expected": round(expected, 4),
                  "total_USD_allocated": alloc, "bond_USD_amount": bond},
        proposed_correction=round(expected, 4),
    )]


def check_alloc_recon(row: dict, ctx: Context) -> list[Finding]:
    """total_USD_allocated + total_USD_unallocated == bond_USD_amount."""
    bond = num(row.get("bond_USD_amount"))
    alloc = num(row.get("total_USD_allocated"))
    unalloc = num(row.get("total_USD_unallocated"))
    if None in (bond, alloc, unalloc) or not bond:
        return []
    if _rel(alloc + unalloc, bond) <= TOL_RECON_REL:
        return []
    return [Finding(
        row["isin"], "issuances", "total_USD_unallocated", "alloc_recon",
        "high", 0.97, "flag", tier="deterministic",
        rationale=f"Allocated + unallocated ({alloc + unalloc:,.0f}) ≠ bond size "
                  f"({bond:,.0f}); one of the three is wrong.",
        evidence={"total_USD_allocated": alloc, "total_USD_unallocated": unalloc,
                  "bond_USD_amount": bond, "sum": round(alloc + unalloc, 2)},
    )]


def check_category_count(row: dict, ctx: Context) -> list[Finding]:
    """pre/post_icma_categories_number == len(non-empty split(';'))."""
    out: list[Finding] = []
    for side in ("pre", "post"):
        n = num(row.get(f"{side}_icma_categories_number"))
        cats = row.get(f"{side}_icma_categories") or ""
        if n is None:
            continue
        actual = len([c for c in cats.split(";") if c.strip()])
        if int(n) == actual:
            continue
        out.append(Finding(
            row["isin"], "issuances", f"{side}_icma_categories_number", "category_count",
            "low", 0.99, "auto_correct", tier="deterministic",
            rationale=f"{side}_icma_categories_number={int(n)} but the list holds "
                      f"{actual} categories.",
            evidence={"stored": int(n), "counted": actual, "categories": cats[:160]},
            proposed_correction=actual,
        ))
    return out


def check_fx_consensus(row: dict, ctx: Context) -> list[Finding]:
    """Implied bond_USD/bond_amount within tol of the per-currency consensus rate.

    The consensus is the median implied rate across the corpus for that currency,
    so this catches a USD figure that disagrees with how the *rest* of the dataset
    converts that currency. Dispositioned `flag` (the true rate is date-dependent
    and only the PDF settles it), never auto-corrected.
    """
    amt = num(row.get("bond_amount"))
    usd = num(row.get("bond_USD_amount"))
    ccy = (row.get("bond_currency") or "").strip()
    if not amt or not usd or ccy not in ctx.fx_consensus:
        return []
    consensus = ctx.fx_consensus[ccy]
    implied = usd / amt
    if consensus <= 0 or _rel(implied, consensus) <= TOL_FX_REL:
        return []
    return [Finding(
        row["isin"], "issuances", "bond_USD_amount", "fx_consensus",
        "medium", 0.7, "flag", tier="deterministic",
        rationale=f"Implied {ccy}->USD rate {implied:.4f} is {_rel(implied, consensus)*100:.0f}% "
                  f"off the corpus median {consensus:.4f} for {ccy}.",
        evidence={"implied_rate": round(implied, 6), "consensus_rate": round(consensus, 6),
                  "currency": ccy, "bond_amount": amt, "bond_USD_amount": usd},
    )]


def check_date_sanity(row: dict, ctx: Context) -> list[Finding]:
    """placement_date must precede maturity_date."""
    p = (row.get("placement_date") or "").strip()
    m = (row.get("maturity_date") or "").strip()
    if not p or not m or p < m:  # ISO dates compare correctly as strings
        return []
    return [Finding(
        row["isin"], "issuances", "maturity_date", "date_sanity",
        "high", 0.99, "flag", tier="deterministic",
        rationale=f"placement_date {p} is not before maturity_date {m}.",
        evidence={"placement_date": p, "maturity_date": m},
    )]


def check_cat_usd_sum(row: dict, ctx: Context) -> list[Finding]:
    """sum(post_allocation_USD) over the ISIN's category rows == total_USD_allocated."""
    isin = row["isin"]
    alloc = num(row.get("total_USD_allocated"))
    cats = ctx.cat_by_isin.get(isin, [])
    if alloc is None or not cats:
        return []
    parts = [num(c.get("post_allocation_USD")) for c in cats]
    parts = [p for p in parts if p is not None]
    if not parts:
        return []
    s = sum(parts)
    if _rel(s, alloc) <= TOL_REL:
        return []
    return [Finding(
        isin, "issuances", "total_USD_allocated", "cat_usd_sum",
        "medium", 0.9, "flag", tier="deterministic",
        rationale=f"Category allocations sum to {s:,.0f} but total_USD_allocated is "
                  f"{alloc:,.0f} ({len(parts)} category rows).",
        evidence={"sum_post_allocation_USD": round(s, 2), "total_USD_allocated": alloc,
                  "n_categories": len(parts)},
    )]


def check_duplicate_isin(row: dict, ctx: Context) -> list[Finding]:
    """An ISIN appearing in >1 issuance row is itself a data-quality signal.

    None in the 100-bond sample; included because at 30k scale the real corpus has
    duplicated ISINs whose rows can diverge. Reports once (on the first row).
    """
    isin = row["isin"]
    if ctx.isin_row_counts.get(isin, 1) <= 1:
        return []
    if ctx.iss_by_isin.get(isin) is not row:
        return []  # only report on the first occurrence
    return [Finding(
        isin, "issuances", "isin", "duplicate_isin",
        "medium", 0.95, "flag", tier="deterministic",
        rationale=f"ISIN appears in {ctx.isin_row_counts[isin]} issuance rows; "
                  f"reconcile or de-duplicate.",
        evidence={"row_count": ctx.isin_row_counts[isin]},
    )]


# --------------------------------------------------------------------------- #
# cat_allocations                                                              #
# --------------------------------------------------------------------------- #

def check_share_def(row: dict, ctx: Context) -> list[Finding]:
    """post_allocation_share_of_total == post_allocation_USD / bond_USD_amount."""
    share = num(row.get("post_allocation_share_of_total"))
    usd = num(row.get("post_allocation_USD"))
    bond = num(row.get("bond_USD_amount"))
    if share is None or usd is None or not bond:
        return []
    expected = usd / bond
    if _rel(share, expected) <= TOL_REL:
        return []
    return [Finding(
        row["isin"], "cat_allocations", "post_allocation_share_of_total", "share_def",
        "low", 0.97, "auto_correct", tier="deterministic",
        rationale=f"Allocation share disagrees with USD÷bond "
                  f"({share:.4f} stored vs {expected:.4f} recomputed).",
        evidence={"stored": share, "expected": round(expected, 6),
                  "post_allocation_USD": usd, "bond_USD_amount": bond,
                  "category": row.get("post_icma_category", "")},
        proposed_correction=round(expected, 6),
    )]


# --------------------------------------------------------------------------- #
# dispatch                                                                     #
# --------------------------------------------------------------------------- #

_ISSUANCE_CHECKS = (
    check_coverage, check_alloc_recon, check_category_count, check_fx_consensus,
    check_date_sanity, check_cat_usd_sum, check_duplicate_isin,
)
_IMPACT_CHECKS = (check_per_million,)
_CAT_CHECKS = (check_share_def,)


def deterministic_findings(table: str, row: dict, ctx: Context) -> list[Finding]:
    """Run every Tier-0 + trail check that applies to `table`'s rows. Pure."""
    out: list[Finding] = []
    if table == "issuances":
        for chk in _ISSUANCE_CHECKS:
            out += chk(row, ctx)
    elif table == "impacts":
        for chk in _IMPACT_CHECKS:
            out += chk(row, ctx)
        out += reconcile_impact_trail(row)   # trail re-derivation (the flagship)
    elif table == "cat_allocations":
        for chk in _CAT_CHECKS:
            out += chk(row, ctx)
    return out
