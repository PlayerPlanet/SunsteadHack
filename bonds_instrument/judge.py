"""The frozen objective judge — the 're-derivable layer'.

This is the 'p99 of bonds': recompute each claimed value from its primitives and
check it reconciles. NEVER calls an LLM, NEVER changes per run. It is the ruler.

A Claim's `view` carries the agent-visible primitives. `passes(view)` recomputes
the claimed value and returns True iff it reconciles within tolerance. Judge-
*uncatchable* corruptions (e.g. a wrong unit label) leave the arithmetic intact,
so `passes` returns True even though the value is semantically wrong — that gap is
exactly where reasoning (not arithmetic) has to earn its keep.
"""


def _rel_close(a: float, b: float, tol: float) -> bool:
    denom = abs(b) if b else 1.0
    return abs(a - b) / denom <= tol


def passes(view: dict) -> bool:
    """Deterministic re-derivation. True = reconciles, False = provably inconsistent."""
    kind = view["kind"]

    if kind == "per_million":
        bond = view["bond_USD_amount"]
        if not bond:
            return True  # cannot judge without a denominator -> not our call
        expected = view["impact_value"] / (bond / 1e6)
        return _rel_close(view["impact_per_million_USD"], expected, tol=1e-3)

    if kind == "coverage":
        bond = view["bond_USD_amount"]
        if not bond:
            return True
        expected = 100.0 * view["total_USD_allocated"] / bond
        return abs(view["allocation_coverage_pct"] - expected) <= 0.1

    if kind == "alloc_recon":
        bond = view["bond_USD_amount"]
        if not bond:
            return True
        return _rel_close(view["total_USD_allocated"] + view["total_USD_unallocated"], bond, tol=1e-4)

    raise ValueError(f"unknown claim kind {kind!r}")
