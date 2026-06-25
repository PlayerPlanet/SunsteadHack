# The Bonds Boundary Instrument — build spec

**What this is:** NOT a data-quality agent (that's the Arctal take-home). This is the
*instrument* that measures **how far any bond-checking agent can be trusted before a
human is needed**, on real green-bond data, with a **frozen objective judge** that makes
the measurement honest. Drop in any agent → get its trustworthy region. Agent-agnostic.

> The manifesto, in the one domain everyone says you can't measure: *"we can't yet build
> the bond agent that knows its own edge — but we can measure exactly where anyone's bond
> agent's edge is."*

Data: `2026-06-23_100-bond-sample-takehome/` (issuances, cat_allocations, geo_allocations,
impacts). "The only truth is the PDFs" — we don't have them, so the judge is built from
what's **re-derivable in the data itself** plus **manufactured ground truth**.

---

## The three pieces that make it work

### 1. The objective judge = the re-derivable layer (FROZEN, no LLM, ungameable)
Every value ships with arithmetic you can recompute. This is the "p99 of bonds." All
checks verified against real rows (Belgium BE0000346552 reconciles to the cent):

| check_id | formula | tol |
|---|---|---|
| `per_million` | `impact_per_million_USD == impact_value / (denom_USD/1e6)`; `denom_USD` = bond_USD_amount if source_trail says `denom=bond`, else allocation USD if `denom=allocation` | rel 1e-3 |
| `coverage` | `allocation_coverage_pct == 100 * total_USD_allocated / bond_USD_amount` | 0.1pp |
| `alloc_recon` | `total_USD_allocated + total_USD_unallocated == bond_USD_amount` | rel 1e-4 |
| `cat_usd_sum` | `sum(post_allocation_USD for isin) == total_USD_allocated` | rel 1e-3 |
| `share_def` | `post_allocation_share_of_total == post_allocation_USD / bond_USD_amount` | rel 1e-3 |
| `category_count` | `pre_icma_categories_number == len(non-empty split(pre_icma_categories, ';'))`; same for post | exact |
| `fx_consensus` | `bond_USD_amount / bond_amount` within tol of the per-(currency, placement-month) **median implied rate derived from the dataset itself** | rel 2e-2 |
| `trail_subsum` | parse narrated components from `*_source_trail` (`"A (222M EUR, 68kt) and B (768M EUR, 1512kt) … total 990M … 1580kt"`) → check `A+B == total` | rel 1e-2 |

`judge.py` exposes `rederive(row, context) -> list[CheckResult]` where each result is
`{check_id, passed, stored, expected, tol}`. **It never calls an LLM and never changes
per run — it is the ruler.**

### 2. Manufactured ground truth = perturbation (contamination-proof)
Re-derivation alone tells you the data is internally (in)consistent. To measure an
*agent's* trustworthy region you need to know which rows are actually wrong. We don't have
the PDFs, so we **mint known errors at runtime** (memorization can't help):

Pick rows that pass ALL re-derivable checks (the clean set). Inject one corruption from a
fixed catalog, recording `(isin, field, corruption_type, original, corrupted)` as the
ground-truth label:

| corruption | what it does | **judge-catchable?** |
|---|---|---|
| `decimal_shift` | ×10 / ÷10 an `impact_value` | YES (breaks `per_million`) |
| `recon_break` | nudge `total_USD_unallocated` a few % | YES (breaks `alloc_recon`) |
| `share_corrupt` | scale one cat `post_allocation_USD` | YES (breaks `cat_usd_sum`/`share_def`) |
| `count_mismatch` | bump `*_categories_number` by 1 | YES (breaks `category_count`) |
| `unit_swap` | relabel tCO2e↔ktCO2e (value /1000, unit unchanged) | **NO — needs reasoning/world-knowledge** |
| `category_swap` | replace `post_icma_category` with a different ICMA category the `source_trail` text contradicts | **NO — needs semantic judgment** |

**This split is the whole demo.** Judge-catchable errors measure whether an agent matches
the deterministic floor. Judge-*un*catchable-but-truth-known errors measure whether the
agent's **reasoning extends the region beyond that floor** — exactly where an LLM should
help and the dumb agent should *escalate, not false-clear*.

`perturb.py`: `build_stream(clean_rows, rate=0.4, seed=…) -> list[Task]` where each Task
carries the agent-visible view (value + source_trail + neighbors) and a *hidden* label.

### 3. The drift axis = distance-from-vanilla (deterministic)
The region recedes along an axis of "how weird is this bond," computed from structural
features only — `drift.py: drift_score(isin) -> float in [0,1]`:
`n_post_categories` · multi-currency flag · `1 - allocation_coverage` · source_trail
length/hop-count · `n_source_documents` · `pre_minus_post_category_gap`. Weighted, normalized,
binned into ~5 levels.

---

## The instrument loop

`instrument.py: run(agent, tasks) -> Scorecard`

```
for task in tasks (mix of clean + perturbed, spanning all drift bins):
    decision = agent.review(task.view)        # verdict ∈ {ok, error, escalate}, confidence, rationale
    # agent NEVER sees task.label or the judge
    if decision.verdict == "escalate":
        bucket as justified_ask (label was error) or over_ask (label clean & judge-rederivable)
    else:
        score decision.verdict vs task.label:
            error & poisoned   -> TP (caught)
            ok    & poisoned   -> FALSE-CLEAR  ← the dangerous error (acted past its edge)
            error & clean      -> false alarm
            ok    & clean      -> correct clear
```

Aggregate **per drift bin**: `escalation_rate`, `autonomous_correctness` (precision/recall
on non-escalated), and the headline **`false_clear_rate`**.

### The agent interface (agent-agnostic) — `agents.py`
`Protocol: review(view) -> Decision`. The view is bounded: value, its `source_trail`,
sibling fields. No judge, no label. Two reference agents:
- **`DumbAgent`** (the frozen baseline whose region we measure): catches only what a trivial
  rule sees (nulls/format), and **escalates anything above a drift threshold or anything it
  has no rule for**. No API key needed.
- **`LLMAgent`** (Haiku first pass → Sonnet on low-confidence): reads value + source_trail,
  reasons, returns ok/error/escalate + confidence. The agent whose region should be *wider*.

---

## The artifact (the payoff)

`report.py` →
- **Headline curve:** `false_clear_rate` and `escalation_rate` vs drift bin, per agent. The
  **trustworthy region** = the drift range where `false_clear_rate ≈ 0`. Where it spikes = the edge.
- **Comparative (the bend):** DumbAgent vs LLMAgent on the same axes → the region the LLM's
  reasoning *adds*, especially on the judge-uncatchable corruptions.
- `findings.jsonl` (machine) + `REGIONS.md` (human): *"Agent X is trustworthy up to drift Y;
  beyond that, false-clears appear / it correctly escalates."*

---

## Honesty (keep it in the writeup)
The re-derivable layer is the **only** place we hold objective truth. The interpretation
layer (is the category *right*, PDF-only facts) has no judge → measured **only** as escalation
behavior, and the instrument is **blind to confident-wrong there** (you can only *bound* it
with a small, soft, human-audited sample — never certify). The instrument **measures** the
boundary; it never claims the agent *understands* it.

---

## Build order (each step is shippable; first real curve needs NO API key)
1. **`judge.py`** — the 8 re-derivable checks. Sanity-check: they mostly PASS on real rows
   (one pipeline made them) — that's why a clean FAIL is signal.
2. **`perturb.py`** — clean-set selection + the corruption catalog → labeled stream.
3. **`drift.py`** — the drift score.
4. **`agents.py: DumbAgent`** — deterministic, no API.
5. **`instrument.py` + `report.py`** — run DumbAgent across drift bins → **MVP: a real
   trustworthy-region curve, zero LLM cost.** This already proves the instrument.
6. **`agents.py: LLMAgent`** (Anthropic SDK; Haiku→Sonnet) → rerun → the comparative bend.
7. Polish `REGIONS.md` + `findings.jsonl`; write the cost note (cheap-first/expensive-at-the-
   boundary, measured on the 100 sample, extrapolated to 30k).

**MVP milestone = step 5:** a real escalation / false-clear-vs-drift curve for the dumb
agent, fully deterministic. Then the LLM agent visibly widens the region.

Stack: Python, `csv`/`pandas` + Anthropic SDK (optional, only for step 6). Self-contained.
