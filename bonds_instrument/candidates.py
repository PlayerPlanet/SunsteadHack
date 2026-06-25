"""Adapter: run the Arctal take-home data-quality agent as a candidate in this
instrument, so it gets a measured trustworthy region alongside the reference agents.

The take-home deliverable (`../arctal_dq_agent`) is kept clean and benchmark-
agnostic — it only exposes pure per-record checks and a `review()` contract. This
file does the wiring on the *benchmark* side: it converts one claim `view` (the
instrument's bounded, single-value unit) into the row shape the agent's checks
expect, runs exactly the check(s) matching the claim's `kind`, and collapses the
resulting findings into the instrument's `Decision(verdict, confidence, rationale)`.

Two variants, mirroring the agent's own two modes:
  * `dq_agent`      — deterministic tiers only (no API key). Catches the arithmetic
                      corruptions; abstains (escalate) on the content it triages as
                      needing reasoning; false-clears only what its triage misses.
  * `dq_agent:llm`  — adds the agent's Tier-1 reasoning (needs ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the standalone deliverable importable without installing or polluting it.
_DELIVERABLE = Path(__file__).resolve().parent.parent / "arctal_dq_agent"
if str(_DELIVERABLE) not in sys.path:
    sys.path.insert(0, str(_DELIVERABLE))

from agent.checks import check_alloc_recon, check_coverage, check_per_million  # noqa: E402
from agent.data import build_context, load_tables  # noqa: E402
from agent.reasoning import make_reasoner  # noqa: E402
from agent.review import decide  # noqa: E402
from agent.trail import reconcile_impact_trail  # noqa: E402


def _record_from_view(view: dict) -> tuple[str, dict]:
    """Map an instrument claim `view` to (kind, agent-row). The view carries floats;
    the agent's `num()` accepts those, so no stringification is needed. `isin` is
    absent from the view (the instrument hides it) — the agent only needs it to label
    findings, which the instrument ignores, so "" is fine."""
    kind = view["kind"]
    if kind == "per_million":
        return kind, {
            "isin": "", "impact_value": view["impact_value"],
            "impact_per_million_USD": view["impact_per_million_USD"],
            "bond_USD_amount": view["bond_USD_amount"],
            "impact_unit": view.get("impact_unit", ""),
            "impact_metric": view.get("impact_metric", ""),
            "source_trail": view.get("source_trail", ""), "review_notes": "",
        }
    if kind == "coverage":
        return kind, {
            "isin": "", "bond_USD_amount": view["bond_USD_amount"],
            "total_USD_allocated": view["total_USD_allocated"],
            "allocation_coverage_pct": view["allocation_coverage_pct"],
        }
    if kind == "alloc_recon":
        return kind, {
            "isin": "", "bond_USD_amount": view["bond_USD_amount"],
            "total_USD_allocated": view["total_USD_allocated"],
            "total_USD_unallocated": view["total_USD_unallocated"],
        }
    return kind, {"isin": ""}


class DQAgentCandidate:
    """Wraps the take-home agent as an instrument-compatible agent."""

    def __init__(self, use_llm: bool = False):
        # Context (FX consensus, per-metric intensity peers, cross-table indexes) is
        # built once from the real tables — the same corpus the claims come from.
        self._ctx = build_context(load_tables())
        self._reasoner = make_reasoner(use_llm)
        self.name = "dq_agent:llm" if self._reasoner.enabled else "dq_agent"

    def review(self, view: dict):
        kind, row = _record_from_view(view)
        ctx = self._ctx
        if kind == "per_million":
            findings = (check_per_million(row, ctx)
                        + reconcile_impact_trail(row)
                        + self._reasoner.assess_impact(row, ctx))
        elif kind == "coverage":
            findings = check_coverage(row, ctx)
        elif kind == "alloc_recon":
            findings = check_alloc_recon(row, ctx)
        else:
            findings = []
        return decide(findings)  # Decision(verdict, confidence, rationale, findings)
