"""Agents under test. The instrument is agent-agnostic: an agent only sees a
claim's `view` (value + source_trail + drift) and returns a Decision. It NEVER
sees whether the claim was poisoned.

Two deterministic reference agents (no API key):

  * JudgeOnlyAgent   — the truly dumb baseline. Runs the arithmetic judge and
                       nothing else. Catches judge-catchable errors; FALSE-CLEARS
                       every judge-uncatchable one. Its trustworthy region recedes
                       as uncatchable errors appear (high drift).
  * StationarityAgent — judge + a FROZEN 'escalate if drift > T' tripwire (the crude
                       authority-proportional-to-stationarity proxy from the
                       manifesto). Buys safety with blunt escalation.

LLMAgent (optional, needs ANTHROPIC_API_KEY) reasons over the source_trail/unit to
catch some uncatchable errors — extending the region. That's the 'bend'.
"""

import sys
from dataclasses import dataclass

from . import judge


@dataclass
class Decision:
    verdict: str          # "ok" | "error" | "escalate"
    confidence: float = 1.0
    rationale: str = ""


class JudgeOnlyAgent:
    name = "judge_only"

    def review(self, view: dict) -> Decision:
        if not judge.passes(view):
            return Decision("error", 1.0, "arithmetic does not reconcile")
        return Decision("ok", 1.0, "reconciles")


class StationarityAgent:
    """Frozen proxy: judge first, then escalate anything past the drift threshold."""
    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.name = f"stationarity@{threshold}"

    def review(self, view: dict) -> Decision:
        if not judge.passes(view):
            return Decision("error", 1.0, "arithmetic does not reconcile")
        if view.get("drift", 0.0) > self.threshold:
            return Decision("escalate", 1.0, f"drift>{self.threshold}: left trusted region")
        return Decision("ok", 1.0, "reconciles and within trusted region")


class LLMAgent:
    """Optional. Judge first; on a reconciling claim, ask a model whether the value
    is *semantically* plausible (catches unit swaps the arithmetic can't see).
    Falls back to escalate-on-doubt. Requires the `anthropic` package + API key.
    """
    def __init__(self, model: str = "claude-haiku-4-5"):
        import anthropic  # raises if unavailable -> caller guards with has_llm()
        self._client = anthropic.Anthropic()
        self.model = model
        self.name = f"llm:{model}"
        self._calls = 0

    def review(self, view: dict) -> Decision:
        if not judge.passes(view):
            return Decision("error", 1.0, "arithmetic does not reconcile")
        if view["kind"] != "per_million":
            return Decision("ok", 0.7, "no semantic check for this kind")
        # Located autonomy: can you STAND BEHIND this value, or must a human decide? The
        # arithmetic already reconciles, so judge two things — physical plausibility AND
        # whether the provenance lets you verify it.
        prompt = (
            "You audit a green-bond impact figure for an autonomous data pipeline. Decide "
            "whether you can STAND BEHIND the value or must defer to a human.\n"
            "- IMPLAUSIBLE if physically wrong for a bond this size (e.g. a unit mislabel like "
            "tCO2e vs ktCO2e making it ~1000x off).\n"
            "- UNSURE if plausible but the provenance is missing/unverified/approximate (no "
            "concrete derivation you can actually check).\n"
            "- PLAUSIBLE if plausible AND the source trail gives a concrete, checkable derivation.\n"
            f"metric={view.get('impact_metric')} value={view['impact_value']} unit={view.get('impact_unit')} "
            f"intensity={view['impact_per_million_USD']:.2f} per $1M  bond_USD={view['bond_USD_amount']:.0f}\n"
            f"trail: {view.get('source_trail','')[:300]}\n"
            "Reply ONE word: PLAUSIBLE, IMPLAUSIBLE, or UNSURE."
        )
        self._calls += 1
        if self._calls % 25 == 0:
            print(".", end="", file=sys.stderr, flush=True)
        try:
            msg = self._client.messages.create(
                model=self.model, max_tokens=8,
                messages=[{"role": "user", "content": prompt}],
            )
            ans = msg.content[0].text.strip().upper()
        except Exception as e:  # network/rate-limit/etc -> escalate (safe default), never crash
            return Decision("escalate", 0.0, f"llm unavailable: {type(e).__name__}")
        if "IMPLAUSIBLE" in ans:
            return Decision("error", 0.8, "unit/magnitude implausible")
        if "UNSURE" in ans:
            return Decision("escalate", 0.5, "cannot stand behind this one")
        return Decision("ok", 0.7, "plausible")


def has_llm() -> bool:
    import importlib.util
    import os
    return importlib.util.find_spec("anthropic") is not None and bool(os.environ.get("ANTHROPIC_API_KEY"))
