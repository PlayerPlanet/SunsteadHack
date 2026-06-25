# Bonds Boundary Instrument

Measures **how far any bond-checking agent stays trustworthy before a human is needed**,
on real green-bond data — with a frozen, re-derivable objective judge and manufactured
(perturbation) ground truth. Drop in an agent, get its trustworthy region. Agent-agnostic.

This is **not** a data-quality agent. It's the *instrument that measures whether any agent
knows its own edge* — and exactly where that edge currently sits.

## Run

```bash
python -m bonds_instrument          # deterministic agents, no API key, runs in ~1s
python -m bonds_instrument --llm    # also run the LLM agent (needs ANTHROPIC_API_KEY)
```

Outputs the trustworthy-region curves to stdout and writes `artifacts/bonds/{findings.jsonl,REGIONS.md}`.

Data dir defaults to `../2026-06-23_100-bond-sample-takehome`; override with `BONDS_DATA_DIR`.

## How it works (three pieces)

1. **Frozen objective judge** (`judge.py`) — the "p99 of bonds". Recompute each claimed
   value from its primitives (per-million normalization, allocation coverage, allocated +
   unallocated = bond). Never calls an LLM, never changes. It is the ruler.
2. **Manufactured ground truth** (`claims.py`) — keep only claims the judge passes on the
   real data, then inject *known* errors. The catalog splits into **judge-catchable**
   (break the arithmetic) and **judge-uncatchable** (`unit_swap`: tCO2e↔ktCO2e — arithmetic
   still reconciles, but the value is 1000× wrong; only reasoning catches it). Uncatchable
   errors concentrate at high drift (`drift²`), so weirder bonds carry more ambiguity.
3. **Drift axis** (`data.py`) — distance-from-vanilla per bond (n categories, coverage,
   source-trail length, #docs, pre→post category gap), rank-normalized across the corpus.

The instrument (`instrument.py`) runs an agent over the labeled stream — the agent only sees
each claim's value + source_trail + drift, never the label — and scores every non-escalated
answer against the hidden truth, bucketed by drift. The headline metric is **false-clear
rate**: a confidently-wrong answer = the agent acting *past its edge*.

## What the curve shows

- `judge_only` (dumb baseline): false-clear climbs with drift (≈0% → 26%) — its trustworthy
  region recedes as the unit-swaps it can't see appear.
- `stationarity@T` (frozen `escalate if drift>T` proxy): buys safety above T with blunt
  escalation (~75%) — trades autonomy wholesale for zero false-clears.
- `llm` (`--llm`): should hold false-clear ≈ 0 while escalating *less* than the proxy —
  reasoning over the source_trail extends the **autonomous** region. That gap is the bend.

## Honesty

The re-derivable layer is the only place we hold objective truth. The interpretation layer
(is the category *right*, PDF-only facts) has no judge → measured only as escalation
behavior, and the instrument is blind to confident-wrong there. It **measures** the
boundary; it never claims an agent *understands* it.
