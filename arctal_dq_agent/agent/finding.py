"""The single unit of agent output.

Every check — deterministic or LLM — emits zero or more `Finding`s. A Finding is
deliberately split into two audiences (see README, "Two output channels"):

  * machine fields (`check_id`, `severity`, `confidence`, `disposition`,
    `evidence`, `proposed_correction`) -> `findings.jsonl`, for their AI tooling;
  * one human-facing `rationale` line -> `REPORT.md`, for a domain expert to triage.

A Finding never contains a wall of text. The `rationale` is one sentence; the
numbers live in `evidence` where a tool — not a human — can consume them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# How loud is this? Used only to rank the human report; not a probability.
SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}

# The three located-autonomy dispositions (see README, "Tier 2 — disposition").
#   auto_correct: the fix is objectively determined (a recomputed number).
#   flag:         a real issue whose fix is debatable -> human triage.
#   escalate:     genuinely ambiguous / only the PDF can resolve -> abstain.
DISPOSITIONS = ("auto_correct", "flag", "escalate")


@dataclass
class Finding:
    isin: str
    table: str          # issuances | impacts | cat_allocations | geo_allocations
    field: str          # the column the finding is about
    check_id: str       # stable id; documented in CHECKS (see checks docstrings)
    severity: str       # high | medium | low
    confidence: float   # 0..1, the agent's confidence in the finding itself
    disposition: str    # auto_correct | flag | escalate
    rationale: str      # ONE line, human-facing
    evidence: dict[str, Any] = field(default_factory=dict)
    proposed_correction: Any = None
    tier: str = "deterministic"  # deterministic | trail | llm — which layer fired

    def to_json(self) -> dict[str, Any]:
        d = {
            "isin": self.isin,
            "table": self.table,
            "field": self.field,
            "check_id": self.check_id,
            "severity": self.severity,
            "confidence": round(self.confidence, 3),
            "disposition": self.disposition,
            "tier": self.tier,
            "rationale": self.rationale,
            "evidence": self.evidence,
        }
        if self.proposed_correction is not None:
            d["proposed_correction"] = self.proposed_correction
        return d
