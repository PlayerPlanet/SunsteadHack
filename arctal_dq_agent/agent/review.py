"""Tier 2 — disposition + the clean per-record decision used everywhere.

`assess_record` is the one place a record's findings come from: deterministic
checks + trail re-derivation + (optional) LLM reasoning, combined. It is a pure
function of `(table, row, context, reasoner)`, separated from all I/O and from the
LLM transport — which is what makes it testable and benchmarkable.

`review(record) -> Decision` collapses those findings into a single verdict for an
*autonomous* setting: `ok` (stands behind the value), `error` (a data-quality
issue), or `escalate` (defer to a human). This is the exact contract a benchmark
or the main pipeline wraps to ask "can this agent be trusted here, or must it ask
a human?" — without depending on any of the reporting/I/O code.
"""

from __future__ import annotations

from dataclasses import dataclass

from .checks import deterministic_findings
from .data import Context, build_context, load_tables
from .finding import Finding
from .reasoning import NullReasoner, make_reasoner

# disposition -> the autonomous verdict it implies
_VERDICT = {"auto_correct": "error", "flag": "error", "escalate": "escalate"}
# precedence when a record yields several findings: a concrete issue beats a defer
_PRECEDENCE = {"error": 2, "escalate": 1, "ok": 0}


@dataclass
class Decision:
    verdict: str       # ok | error | escalate
    confidence: float
    rationale: str
    findings: list[Finding] = None  # the underlying findings (for the report/audit)


def assess_record(table: str, row: dict, ctx: Context, reasoner=None) -> list[Finding]:
    """All findings for one record. Pure given (ctx, reasoner). The core seam."""
    reasoner = reasoner or NullReasoner()
    out = deterministic_findings(table, row, ctx)
    if table == "impacts":
        out += reasoner.assess_impact(row, ctx)
    elif table == "cat_allocations":
        out += reasoner.assess_category(row, ctx)
    return out


def decide(findings: list[Finding]) -> Decision:
    """Collapse findings to one autonomous verdict (error > escalate > ok)."""
    if not findings:
        return Decision("ok", 0.9, "no data-quality issue found", [])
    best = max((_VERDICT[f.disposition] for f in findings), key=lambda v: _PRECEDENCE[v])
    drivers = [f for f in findings if _VERDICT[f.disposition] == best]
    top = max(drivers, key=lambda f: f.confidence)
    return Decision(best, top.confidence, top.rationale, findings)


# --------------------------------------------------------------------------- #
# The benchmark / pipeline contract: review(record) -> Decision.              #
# Lazily builds a shared context + reasoner so the bare `review(record)` form  #
# works out of the box; pass them explicitly for performance at scale.         #
# --------------------------------------------------------------------------- #

_CTX: Context | None = None
_REASONER = None


def _shared(use_llm: bool):
    global _CTX, _REASONER
    if _CTX is None:
        _CTX = build_context(load_tables())
    if _REASONER is None:
        _REASONER = make_reasoner(use_llm)
    return _CTX, _REASONER


def review(record: dict, context: Context | None = None, reasoner=None,
           *, use_llm: bool = True) -> Decision:
    """Per-record verdict. `record` is a CSV row dict plus a `table` key
    (defaults to 'impacts' — the densest ambiguity surface — if absent)."""
    table = record.get("table") or record.get("__table__") or "impacts"
    if context is None or reasoner is None:
        ctx, rsn = _shared(use_llm)
        context = context or ctx
        reasoner = reasoner or rsn
    return decide(assess_record(table, record, context, reasoner))
