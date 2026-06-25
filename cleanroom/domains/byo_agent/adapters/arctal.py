"""Arctal green-bond review agent adapter for byo_agent vertical.

Wraps the arctal LLM agent and rule-based variants to conform to the
byo_agent contract: invoke(input_text, config) -> {result: str, tokens: int}

The agent receives a green-bond claim (JSON-encoded view) and returns a verdict:
  - "ok" if the claim passes all checks
  - "error" if the claim contains a provable error
  - "escalate" if the claim is ambiguous or requires human review

Two modes:
  - rule: deterministic, uses the judge only (NO network, config-insensitive)
  - llm: calls Anthropic Haiku with a configurable system_prompt for reasoning
"""

import json

from bonds_instrument import claims, judge


class ArctalReviewAgent:
    """Arctal green-bond review agent.

    Args:
        mode: "rule" (deterministic) or "llm" (calls Anthropic).
        model: Model ID for LLM mode (default: claude-haiku-4-5-20251001).
    """

    def __init__(self, mode: str = "rule", model: str = "claude-haiku-4-5-20251001"):
        self.mode = mode
        self.model = model
        self._client = None

    def invoke(self, input_text: str, config: dict) -> dict:
        """Invoke the agent on a green-bond claim.

        Args:
            input_text: JSON-encoded claim view (dict with kind, value, unit, etc.)
            config: Agent config dict with system_prompt, temperature, top_p, max_tokens.

        Returns:
            Dict with:
              - result: str, one of "ok"|"error"|"escalate"
              - tokens: int, token count (0 for rule mode)
        """
        try:
            view = json.loads(input_text)
        except (json.JSONDecodeError, ValueError):
            return {"result": "escalate", "tokens": 0}

        if self.mode == "rule":
            return self._invoke_rule(view)
        elif self.mode == "llm":
            return self._invoke_llm(view, config)
        else:
            return {"result": "escalate", "tokens": 0}

    def _invoke_rule(self, view: dict) -> dict:
        """Deterministic rule-based verdict.

        Returns "error" if judge.passes(view) is False, else "ok".
        This is the deterministic floor: it can only catch arithmetic errors
        (judge-catchable corruptions), not semantic/unit errors.
        """
        try:
            if judge.passes(view):
                return {"result": "ok", "tokens": 0}
            else:
                return {"result": "error", "tokens": 0}
        except Exception:
            return {"result": "escalate", "tokens": 0}

    def _invoke_llm(self, view: dict, config: dict) -> dict:
        """Two-tier LLM-based reasoning (mirroring bonds_instrument/agents.py::LLMAgent).

        Tier 0 (deterministic, NO LLM, no tokens):
          - If arithmetic does NOT reconcile (judge.passes=False) → "error"

        Tier 1 (LLM, only for reconciling per_million):
          - If arithmetic reconciles AND kind=="per_million" → call Anthropic Haiku
          - Maps reply words to verdicts:
            * IMPLAUSIBLE -> "error"
            * UNSURE -> "escalate"
            * PLAUSIBLE or else -> "ok"

        Non-per_million reconciling claims: "ok" (no LLM, no tokens).

        This is faithful to the real arctal agent and avoids wasting tokens
        on claims that already fail arithmetic.
        """
        try:
            # TIER 0: Check deterministic judge FIRST (no LLM call).
            if not judge.passes(view):
                return {"result": "error", "tokens": 0}

            # If kind is not per_million and reconciles, return ok (no LLM).
            kind = view.get("kind", "unknown")
            if kind != "per_million":
                return {"result": "ok", "tokens": 0}

            # TIER 1: Only for reconciling per_million claims, call LLM.
            if self._client is None:
                import anthropic
                self._client = anthropic.Anthropic()
        except ImportError:
            return {"result": "escalate", "tokens": 0}

        try:
            system_prompt = config.get(
                "system_prompt",
                "You are a green-bond data auditor. Review claims for accuracy."
            )
            temperature = config.get("temperature", 0.3)
            top_p = config.get("top_p", 1.0)
            max_tokens = config.get("max_tokens", 256)

            # Build the user prompt from claim fields.
            user_prompt = self._build_user_prompt(view, kind)

            # Call Anthropic.
            msg = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Extract response.
            reply = msg.content[0].text.strip().upper() if msg.content else ""
            input_tokens = msg.usage.input_tokens
            output_tokens = msg.usage.output_tokens
            total_tokens = input_tokens + output_tokens

            # Map reply to verdict.
            if "IMPLAUSIBLE" in reply:
                return {"result": "error", "tokens": total_tokens}
            elif "UNSURE" in reply:
                return {"result": "escalate", "tokens": total_tokens}
            else:
                return {"result": "ok", "tokens": total_tokens}

        except Exception:
            # Safe default: never crash, always escalate on any error.
            return {"result": "escalate", "tokens": 0}

    def _build_user_prompt(self, view: dict, kind: str) -> str:
        """Build a user prompt for the claim."""
        if kind == "per_million":
            impact_metric = view.get("impact_metric", "unknown")
            impact_value = view.get("impact_value", "?")
            impact_unit = view.get("impact_unit", "unknown")
            intensity = view.get("impact_per_million_USD", 0.0)
            bond_usd = view.get("bond_USD_amount", 0.0)
            source_trail = view.get("source_trail", "")[:300]

            return (
                f"A green bond reports an impact of {impact_metric}={impact_value} {impact_unit}, "
                f"intensity {intensity:.2f} per $1M, bond size ${bond_usd:.0f}.\n"
                f"Source trail: {source_trail}\n"
                f"Is this claim PLAUSIBLE, IMPLAUSIBLE (e.g., unit mislabel ~1000x wrong), "
                f"or UNSURE (missing/unverifiable provenance)?"
            )
        elif kind == "coverage":
            bond_usd = view.get("bond_USD_amount", 0.0)
            allocated = view.get("total_USD_allocated", 0.0)
            coverage_pct = view.get("allocation_coverage_pct", 0.0)
            source_trail = view.get("source_trail", "")[:300]

            return (
                f"A green bond (${bond_usd:.0f}) allocates ${allocated:.0f}, "
                f"reported coverage {coverage_pct:.1f}%.\n"
                f"Source: {source_trail}\n"
                f"Is this coverage claim PLAUSIBLE, IMPLAUSIBLE, or UNSURE?"
            )
        else:
            # Generic fallback.
            return (
                f"Green bond claim (kind={kind}):\n"
                f"{json.dumps(view, indent=2)[:500]}\n"
                f"Is this PLAUSIBLE, IMPLAUSIBLE, or UNSURE?"
            )


class ArctalPromptProposer:
    """Deterministic proposer for arctal agent config optimization.

    Proposes a fixed ladder of increasingly specific green-bond-auditor
    system prompts, designed to improve detection of semantic/unit errors.
    """

    PROMPT_LADDER = [
        # Baseline: generic auditor
        "You are a green-bond data auditor. Review claims for accuracy.",
        # Enhanced: catch magnitude errors
        "You are a meticulous green-bond auditor. Detect corrupted arithmetic and magnitude errors. "
        "A tCO2e/ktCO2e unit mislabel makes a value ~1000× wrong—catch it.",
        # Strict: catch missing provenance
        "You are a strict green-bond auditor. (1) If arithmetic reconciles, check semantic plausibility. "
        "(2) If provenance is missing or unverifiable, escalate—never guess. "
        "(3) A tCO2e/ktCO2e unit swap makes a value ~1000× wrong.",
        # Expert: full reasoning
        "You are an expert green-bond auditor in a financial pipeline. Your job: "
        "(1) Arithmetic: delegate to the judge. (2) Semantic plausibility: catch unit mislabels, magnitude errors. "
        "(3) Provenance: if unverifiable, escalate. "
        "Never override the judge—if arithmetic breaks, respond 'error'. "
        "For reconciling claims: PLAUSIBLE if semantically sound AND provenance is concrete. "
        "IMPLAUSIBLE if magnitude/unit is wrong (e.g. tCO2e vs ktCO2e ~1000× error). "
        "UNSURE if plausible but provenance is missing/approximate.",
        # Specialized: bond-specific wisdom
        "You are a specialized green-bond auditor optimizing for trustworthiness in automation. "
        "For each claim: (1) Arithmetic reconciles? (answered by the judge.) "
        "(2) Semantic plausibility? Catch unit mislabels (tCO2e↔ktCO2e ≈1000×), absurd magnitudes. "
        "(3) Can you STAND BEHIND this value? Only if provenance is concrete and checkable. "
        "If any doubt on (2) or (3), escalate—a false clear is worse than a false escalation. "
        "Reply: PLAUSIBLE, IMPLAUSIBLE, or UNSURE.",
    ]

    def __init__(self):
        self._idx = 0

    def propose(self, task_spec: dict, history: list) -> "Candidate":
        """Return the next prompt from the ladder.

        Args:
            task_spec: Domain env dict (unused; present for interface compatibility).
            history: Prior accepted candidates (unused; for future adaptive logic).

        Returns:
            Candidate(type="agent_config", params={"config_delta": {"system_prompt": ...}})
        """
        from cleanroom.types import Candidate

        prompt = self.PROMPT_LADDER[self._idx % len(self.PROMPT_LADDER)]
        self._idx += 1

        return Candidate(
            type="agent_config",
            params={"config_delta": {"system_prompt": prompt}},
            reversible=True,
        )


def build_arctal_eval(
    *, seed: int = 7, error_rate: float = 0.40, ambiguous_rate: float = 0.15
) -> list[dict]:
    """Build arctal eval dataset from green-bond claims.

    Deterministic given seed. Labels derive ONLY from claims.poison (planted),
    never from an LLM. The poison function injects deterministic corruptions and
    assigns truth labels: "clean", "error", or "needs_human".

    Args:
        seed: Random seed for deterministic poisoning.
        error_rate: Fraction of claims to inject errors into.
        ambiguous_rate: Fraction of per_million claims to mark needs_human.

    Returns:
        List of JSONL-compatible dicts: {input: json_view, expected: verdict}
    """
    clean_claims = claims.build_clean_claims()
    poisoned = claims.poison(
        clean_claims,
        error_rate=error_rate,
        ambiguous_rate=ambiguous_rate,
        seed=seed,
    )

    eval_data = []
    for claim in poisoned:
        input_json = json.dumps(claim.view, sort_keys=True)
        expected_verdict = {"clean": "ok", "error": "error", "needs_human": "escalate"}[
            claim.truth
        ]
        eval_data.append({"input": input_json, "expected": expected_verdict})

    return eval_data


def write_arctal_eval_jsonl(path: str, **kw) -> None:
    """Write arctal eval dataset to a JSONL file.

    Args:
        path: Path to write JSONL file.
        **kw: Keyword arguments for build_arctal_eval (seed, error_rate, ambiguous_rate).
    """
    eval_data = build_arctal_eval(**kw)
    with open(path, "w") as f:
        for item in eval_data:
            f.write(json.dumps(item) + "\n")
