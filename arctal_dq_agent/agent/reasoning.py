"""Tier 1 — agent/LLM reasoning, only where deterministic checks cannot reach.

This is where the agent earns its keep: judgments over ambiguous, extracted text
that no SQL re-derivation settles. Two deep checks (the brief asks for 2–3, gone
deep, not wide-and-shallow):

  * impact plausibility — is the value/unit physically sane for a bond this size
    (catches a tCO2e<->ktCO2e mislabel, ~1000x off), and is the provenance even
    checkable? Triaged by peer-intensity outliers, pipeline `review_notes`, or a
    trail with no re-derivable arithmetic.
  * category-mapping plausibility — does the reported text / subcategory
    description actually fit the assigned ICMA category, or is it misattributed?

Cost discipline (the 30k story): Tier 1 only runs on the residual the Tier-0
triage selects, a cheap model (Haiku) does the first pass, and only low-confidence
residuals escalate to a stronger model (Sonnet). Every call is counted so the
README's cost figure is *measured*, not guessed.

Two reasoners share one interface so the pipeline is identical with or without a key:
  * `LLMReasoner`  — needs `anthropic` + ANTHROPIC_API_KEY.
  * `NullReasoner` — no key: abstains on the hard cases (escalate), never clears
    them. A confident-wrong auto-clear is the dangerous error; abstention is safe.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

from .data import Context, num
from .finding import Finding

HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-4-6"

OUTLIER_Z = 5.0          # robust sigmas from peer median to call an intensity outlier
_RE_DIV = re.compile(r"[\d,]+(?:\.\d+)?\s*/\s*[\d,]+(?:\.\d+)?\s*M\s*USD")


# --------------------------------------------------------------------------- #
# Triage — decide (deterministically, free) which rows deserve a paid pass.    #
# --------------------------------------------------------------------------- #

def triage_impact(row: dict, ctx: Context) -> str | None:
    """Short reason this impact row needs semantic review, or None to skip it."""
    reasons: list[str] = []
    metric = (row.get("impact_metric") or "").strip()
    pmu = num(row.get("impact_per_million_USD"))
    peer = ctx.pmu_peers.get(metric)
    if peer and pmu is not None and peer.robust_z(pmu) >= OUTLIER_Z:
        reasons.append(f"intensity {pmu:.0f}/$M is ~{peer.robust_z(pmu):.0f}σ off {peer.n} {metric} peers")
    if (row.get("review_notes") or "").strip():
        reasons.append("pipeline review_notes present")
    if not _RE_DIV.search(row.get("source_trail") or ""):
        reasons.append("no re-derivable arithmetic in trail")
    return "; ".join(reasons) or None


def triage_category(row: dict, ctx: Context) -> str | None:
    """Reason this category row needs a mapping-plausibility check, or None."""
    icma = (row.get("pre_icma_category") or "").strip()
    reported = (row.get("pre_category_as_reported") or "").strip()
    desc = (row.get("pre_subcategory_description") or "").strip()
    if not icma or not desc:
        return None
    if reported and reported.lower() == icma.lower():
        return None  # reported label echoes the ICMA bucket -> trivially aligned
    return "reported label/description differs from assigned ICMA category"


# --------------------------------------------------------------------------- #
# No-LLM reasoner — abstain on the hard cases (never auto-clear).              #
# --------------------------------------------------------------------------- #

@dataclass
class _Stats:
    haiku_calls: int = 0
    sonnet_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class NullReasoner:
    """No API key: the semantically-hard rows are escalated, not cleared."""
    enabled = False

    def __init__(self):
        self.stats = _Stats()

    def assess_impact(self, row: dict, ctx: Context) -> list[Finding]:
        why = triage_impact(row, ctx)
        if not why:
            return []
        return [_escalate_impact(row, why, confidence=0.5,
                                 note="no LLM available; semantic plausibility unresolved")]

    def assess_category(self, row: dict, ctx: Context) -> list[Finding]:
        why = triage_category(row, ctx)
        if not why:
            return []
        return [_escalate_category(row, why, confidence=0.5,
                                   note="no LLM available; mapping unresolved")]


# --------------------------------------------------------------------------- #
# LLM reasoner — Haiku first pass, Sonnet on the low-confidence residual.      #
# --------------------------------------------------------------------------- #

class LLMReasoner:
    enabled = True

    def __init__(self, first=HAIKU, strong=SONNET):
        import anthropic  # raises if missing -> caller guards with has_llm()
        self._client = anthropic.Anthropic()
        self.first, self.strong = first, strong
        self.stats = _Stats()

    # -- impact plausibility ------------------------------------------------ #
    def assess_impact(self, row: dict, ctx: Context) -> list[Finding]:
        why = triage_impact(row, ctx)
        if not why:
            return []
        prompt = self._impact_prompt(row, ctx, why)
        verdict, conf, reason = self._ask(prompt, self.first, "haiku")
        if verdict == "UNSURE" or conf < 0.6:  # escalate the doubtful ones to Sonnet
            verdict, conf, reason = self._ask(prompt, self.strong, "sonnet")
        return self._impact_finding(row, why, verdict, conf, reason)

    # -- category mapping --------------------------------------------------- #
    def assess_category(self, row: dict, ctx: Context) -> list[Finding]:
        why = triage_category(row, ctx)
        if not why:
            return []
        prompt = self._category_prompt(row)
        verdict, conf, reason = self._ask(prompt, self.first, "haiku")
        if verdict == "UNSURE" or conf < 0.6:
            verdict, conf, reason = self._ask(prompt, self.strong, "sonnet")
        if verdict == "MISMATCH":
            return [Finding(
                row["isin"], "cat_allocations", "post_icma_category", "category_mapping",
                "medium", conf, "flag", tier="llm",
                rationale=f"Possible misattribution: {reason}"[:200],
                evidence={"pre_icma_category": row.get("pre_icma_category", ""),
                          "as_reported": row.get("pre_category_as_reported", ""),
                          "subcategory_description": (row.get("pre_subcategory_description") or "")[:240],
                          "model_reason": reason[:240]},
            )]
        if verdict == "UNSURE":
            return [_escalate_category(row, why, conf, reason)]
        return []

    # -- LLM plumbing ------------------------------------------------------- #
    def _heartbeat(self) -> None:
        """Live progress to stderr so a multi-minute run never looks hung."""
        s = self.stats
        n = s.haiku_calls + s.sonnet_calls
        line = f"  tier-1: {n} llm calls (haiku {s.haiku_calls}, sonnet {s.sonnet_calls})"
        if sys.stderr.isatty():
            print("\r" + line, end="", file=sys.stderr, flush=True)  # update in place
        elif n % 25 == 0:                                            # piped: periodic line
            print(line, file=sys.stderr, flush=True)

    def _ask(self, prompt: str, model: str, tag: str) -> tuple[str, float, str]:
        """One model call -> (VERDICT, confidence, one-line reason). Never raises."""
        try:
            msg = self._client.messages.create(
                model=model, max_tokens=120,
                messages=[{"role": "user", "content": prompt}],
            )
            setattr(self.stats, f"{tag}_calls", getattr(self.stats, f"{tag}_calls") + 1)
            u = getattr(msg, "usage", None)
            if u:
                self.stats.input_tokens += u.input_tokens
                self.stats.output_tokens += u.output_tokens
            self._heartbeat()
            return self._parse(msg.content[0].text)
        except Exception as e:  # network / rate-limit / parse -> abstain, never crash
            self._heartbeat()
            return "UNSURE", 0.0, f"llm unavailable: {type(e).__name__}"

    @staticmethod
    def _parse(text: str) -> tuple[str, float, str]:
        t = text.strip()
        verdict = "UNSURE"
        for v in ("IMPLAUSIBLE", "PLAUSIBLE", "MISMATCH", "MATCH", "UNSURE"):
            if v in t.upper():
                verdict = v
                break
        m = re.search(r"conf(?:idence)?[=:\s]+([01](?:\.\d+)?)", t, re.I)
        conf = float(m.group(1)) if m else 0.6
        reason = re.sub(r"\s+", " ", t)[:200]
        return verdict, conf, reason

    @staticmethod
    def _impact_prompt(row: dict, ctx: Context, why: str) -> str:
        metric = (row.get("impact_metric") or "").strip()
        peer = ctx.pmu_peers.get(metric)
        peer_line = f"peer median for this metric ≈ {peer.median:.1f}/$M (n={peer.n})." if peer else "no peer baseline."
        return (
            "You audit one impact figure from an automated green-bond data pipeline. "
            "The arithmetic already reconciles; judge whether you can STAND BEHIND the value.\n"
            "- IMPLAUSIBLE: physically wrong for a bond this size (e.g. a unit mislabel such "
            "as tCO2e vs ktCO2e making it ~1000x off, or an impossible intensity).\n"
            "- UNSURE: plausible but provenance is missing/approximate — no checkable derivation.\n"
            "- PLAUSIBLE: physically sane AND the trail gives a concrete, checkable derivation.\n"
            f"metric={metric} value={row.get('impact_value')} unit={row.get('impact_unit')} "
            f"intensity={row.get('impact_per_million_USD')}/$M bond_USD={row.get('bond_USD_amount')}\n"
            f"{peer_line}\n"
            f"trail: {(row.get('source_trail') or '')[:280]}\n"
            f"review_notes: {(row.get('review_notes') or '')[:200]}\n"
            f"(triaged because: {why})\n"
            "Reply: VERDICT=<PLAUSIBLE|IMPLAUSIBLE|UNSURE> conf=<0..1> reason=<≤15 words>."
        )

    @staticmethod
    def _category_prompt(row: dict) -> str:
        return (
            "You audit a green-bond use-of-proceeds classification. The pipeline assigned an "
            "ICMA category to a project. Decide whether the reported description fits it.\n"
            "ICMA green categories include: Renewable Energy, Energy Efficiency, Clean "
            "Transportation, Sustainable Water and Wastewater Management, Pollution Prevention "
            "and Control, Green Buildings, Climate Change Adaptation, Environmentally "
            "Sustainable Management of Living Natural Resources, Terrestrial and Aquatic "
            "Biodiversity, Eco-efficient/Circular Economy products.\n"
            f"assigned_ICMA_category: {row.get('pre_icma_category','')}\n"
            f"as_reported_by_issuer: {row.get('pre_category_as_reported','')}\n"
            f"subcategory_description: {(row.get('pre_subcategory_description') or '')[:280]}\n"
            f"eligibility: {(row.get('pre_eligibility_criteria') or '')[:160]}\n"
            "Reply: VERDICT=<MATCH|MISMATCH|UNSURE> conf=<0..1> reason=<≤15 words, name the "
            "better category if MISMATCH>."
        )

    def _impact_finding(self, row, why, verdict, conf, reason) -> list[Finding]:
        if verdict == "IMPLAUSIBLE":
            return [Finding(
                row["isin"], "impacts", "impact_value", "impact_plausibility",
                "high", conf, "flag", tier="llm",
                rationale=f"Impact value implausible: {reason}"[:200],
                evidence={"impact_metric": row.get("impact_metric", ""),
                          "impact_value": row.get("impact_value"),
                          "impact_unit": row.get("impact_unit"),
                          "intensity_per_M": row.get("impact_per_million_USD"),
                          "triage": why, "model_reason": reason[:240]},
            )]
        if verdict == "UNSURE":
            return [_escalate_impact(row, why, conf, reason)]
        return []  # PLAUSIBLE -> the agent stands behind it; no finding


# --------------------------------------------------------------------------- #
# Shared escalation builders (used by both reasoners).                        #
# --------------------------------------------------------------------------- #

def _escalate_impact(row, why, confidence, note) -> Finding:
    docs = row.get("post_source_detail") or ""
    return Finding(
        row["isin"], "impacts", "impact_value", "impact_plausibility",
        "medium", confidence, "escalate", tier="llm",
        rationale=f"{row.get('impact_metric','')}: can't verify from extracted data — {note}.",
        evidence={"triage": why, "review_notes": (row.get("review_notes") or "")[:200],
                  "source_detail": docs[:200], "trail": (row.get("source_trail") or "")[:200]},
    )


def _escalate_category(row, why, confidence, note) -> Finding:
    return Finding(
        row["isin"], "cat_allocations", "post_icma_category", "category_mapping",
        "low", confidence, "escalate", tier="llm",
        rationale=f"Category mapping unresolved: {note}"[:200],
        evidence={"pre_icma_category": row.get("pre_icma_category", ""),
                  "as_reported": row.get("pre_category_as_reported", ""),
                  "subcategory_description": (row.get("pre_subcategory_description") or "")[:200]},
    )


def make_reasoner(use_llm: bool):
    """Pick the reasoner: LLM if requested AND available, else the abstaining one."""
    if use_llm and has_llm():
        return LLMReasoner()
    return NullReasoner()


def has_llm() -> bool:
    import importlib.util
    return importlib.util.find_spec("anthropic") is not None and bool(os.environ.get("ANTHROPIC_API_KEY"))
