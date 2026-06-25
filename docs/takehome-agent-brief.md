# Build brief: green-bond data-quality agent

You are building a self-contained agent for an engineering take-home. The grader will
point you at two things in the working directory:
- the sample data: `2026-06-23_100-bond-sample-takehome/` (CSVs + `data_dictionary.xlsx`)
- the take-home PDF (the task statement)

**Read both first.** This brief gives you the architecture, the data facts already
verified against the real files (so you don't re-derive them), and the bar for "great".
Build a **clean, standalone, runnable repo** — do not reference any external "benchmark"
or "manifesto"; this is the deliverable a hiring team reads.

---

## The task (from the take-home)

> Build an agent that helps us search for, flag, and (where sensible) correct data-quality
> issues in this dataset. We're specifically interested in checks that go **beyond what plain
> SQL or simple code-based checks can do** — reasoning over ambiguous, extracted data where an
> agent earns its keep. It's fine (encouraged) to use deterministic code/SQL as part of the
> system; we just don't want only that. Communication is the crux. README must let us run it
> with minimal effort. Credible cost/performance story for scaling to 30k+ bonds.

Time budget ~4–5 hours: **judgment and communication over comprehensiveness.** Go DEEP on a
few hard checks; don't go wide-and-shallow.

Key framing from the prompt, do not ignore:
- **"The only truth is the PDFs."** The CSVs are *extracted* data; the real ground truth is
  the source documents, which you do **not** have. So the agent reasons over the extracted
  values + their `*_source_trail` narration, and **escalates to human/PDF verification** where
  the data alone can't resolve it.
- **`data_quality_flags` is their own pipeline's output — treat it as background, NOT a target.**
  Don't reproduce or "clear" it. Where your checks overlap it, add the *why* it doesn't.
- They are not green-bond domain experts and will **use AI to run/check it but humans read the
  README** — so no AI slop; clear, honest, concise.

---

## Data facts (verified against the real files — trust but confirm in `data_dictionary.xlsx`)

Files & grain:
- `issuances.csv` — one row per bond (mostly), with `*_source_trail` columns. NOTE: ~2118 rows
  but ~1598 unique ISINs → **duplicate ISINs exist** (itself a data-quality signal).
- `cat_allocations.csv` — per-category allocations (pre/post ICMA, subcategory free-text).
- `geo_allocations.csv` — per-geography allocations.
- `impacts.csv` — impact metrics (e.g. tCO2e), with per-$M normalisations and `review_notes`.

**Re-derivable arithmetic** (this is where deterministic checks are cheap, exact, and scale to
30k — all verified on real rows, e.g. Belgium `BE0000346552` reconciles to the cent):
- `impact_per_million_USD == impact_value / (bond_USD_amount / 1e6)`. The `source_trail` even
  states the denominator basis (`denom=bond` vs `denom=allocation`) — respect it.
- `allocation_coverage_pct == 100 * total_USD_allocated / bond_USD_amount`.
- `total_USD_allocated + total_USD_unallocated == bond_USD_amount`.
- `sum(post_allocation_USD) per ISIN == total_USD_allocated`; and
  `post_allocation_share_of_total == post_allocation_USD / bond_USD_amount`.
- `pre/post_icma_categories_number == len(split(pre/post_icma_categories, ';'))` (drop blanks).

**The `*_source_trail` columns narrate the derivation, with checkable sub-arithmetic**, e.g.:
`"Railway combines SNCB (222M EUR, 68kt) and INFRABEL (768M EUR, 1512kt) for total 990M EUR
and 1580kt"` → `222+768=990` ✓, `68+1512=1580` ✓. This is the flagship "beyond SQL" surface:
an agent can read the narration, re-derive it, and check it supports the stored value.

Other signals: `impacts.review_notes` (e.g. `"PMU 64455 exceeds cap 50000 MWh/$M"`,
`"trail provides no derivation"`); `pre_source_documents`/`post_source_documents` carry
`https://source.arctal.ai/...` URLs (an optional stretch: fetch the cited PDF for true
verification; otherwise escalate WITH the URL so a human knows exactly what to open).

---

## Architecture — tiered (deterministic interior → agent reasoning → disposition)

The thesis the grader is testing: an agent that does the objective work itself and **knows
when to hand a genuinely-ambiguous case to a human, explicitly.** Build three tiers:

**Tier 0 — deterministic checks (run on all rows, ~free, scales to 30k).** The re-derivable
arithmetic above + cross-table consistency (same ISIN's `bond_USD_amount` agrees across files),
duplicate-ISIN divergence, date sanity (`placement < maturity`), FX consistency (implied
`bond_USD/bond_amount` vs a per-currency consensus derived from the dataset). Necessary for
trust and cost, but NOT where the agent earns its keep. Use it as a triage filter into Tier 1.

**Tier 1 — agent/LLM reasoning (only where deterministic can't reach — "earns its keep").**
Pick 2–3 and go deep:
- **source_trail reconciliation (flagship):** read the narration, re-derive its stated
  arithmetic, confirm it supports the stored value and is internally consistent.
- **category-mapping plausibility:** does `pre_category_as_reported` / `pre_subcategory_description`
  actually match the assigned ICMA `pre_icma_category`? Flag mismatches; escalate the genuinely
  debatable ones.
- **impact plausibility:** unit sanity (tCO2e vs ktCO2e — a mislabel is ~1000× off), per-$M
  outliers vs peers, `reported` vs `estimated` emissions divergence judged against the trails.

**Tier 2 — disposition (the located-autonomy decision, per finding):**
- `auto_correct` — ONLY where the fix is objectively determined (a recomputed number). Emit the
  corrected value + evidence. ("where sensible, correct.")
- `flag` — real issue, fix debatable → human triage with a crisp rationale + evidence.
- `escalate` — genuinely ambiguous / only-the-PDF-can-resolve → **abstain from correcting**, say
  *why*, and point to the exact source document + what to check.
- **Never silently auto-correct an ambiguous field.** Erring toward flag/escalate is correct: a
  confident-wrong auto-correction is the dangerous error.

---

## Output — two deliberate channels (this is "communication is the crux")

1. **`findings.jsonl`** (machine-consumable, for their AI tools): one finding per line —
   `{isin, table, field, check_id, severity, confidence, disposition, rationale, evidence
   (the conflicting values + source_trail excerpt), proposed_correction?}`.
2. **`REPORT.md`** (human triage, for the domain expert): concise, ranked, grouped by
   disposition + severity, ONE line of *why* per finding, rollup counts. A non-engineer triages
   it in minutes — no walls of text. Make the human-vs-tool split a deliberate, stated choice.

Each `check_id` is documented (what it checks, why, how it decides). Every flag carries evidence
+ confidence. Be honest about limits in the README ("we don't have the PDFs; Tier-1 reasons over
extracted data + source_trail; some checks are heuristic and labelled as such").

---

## Cost / performance for 30k+ (a graded criterion)

The funnel IS the story: Tier 0 on all 30k for ~free; Tier 1 only on the flagged subset; a cheap
model for the first reasoning pass, escalating to a stronger model only on the hard residual;
batch + cache by `(field, source_trail hash)`. **Measure real cost on the 100-bond sample and
extrapolate to 30k with stated assumptions** — a measured number, not a guess.

---

## Engineering / repo requirements

- **Self-contained, runs with one command.** Python (their stack is python/typescript). Minimal
  deps. Provide a mode that runs the Tier-0 (deterministic) checks **with no API key**, and a
  Tier-1 mode that uses an LLM when a key is present (Anthropic SDK; default to a current Claude
  model). Ship example output on the sample data.
- **Clean core for testability:** put the per-record decision in a clean, pure-ish function, e.g.
  `assess(record, context) -> list[Finding]` (and/or a `verdict(claim) -> {ok|flag|escalate}`),
  separated from I/O and the LLM call. Document each check. A few unit tests on the deterministic
  checks go a long way for trust.
- **Human-written README:** how to run (minimal effort), key design decisions, the cost story,
  example output, honest "what I'd do with more time / known limits." No AI slop.

What they explicitly evaluate: hard ambiguity-laden checks vs trivial ones · clarity of findings
to a non-engineer · clarity of code to engineers · credible 30k cost story · runs cleanly · honest,
human-readable README.

---

## (For the team only — not part of the Arctal deliverable) benchmark adapter

We separately benchmark this agent against a bare "only-LLM" baseline. To enable that WITHOUT
polluting the clean submission, just keep the per-record decision exposed as a pure function:

```python
# verdict over ONE claim/record, no I/O, no label visible
def review(record) -> Decision:  # Decision(verdict ∈ {"ok","error","escalate"}, confidence, rationale)
    ...
```

`ok` = stands behind the value, `error` = data-quality issue, `escalate` = needs a human. That's
all we need to wrap it as a candidate; the team will wire it into the existing instrument
(`bonds_instrument/` in the sibling repo). Don't build the benchmark — just keep `review()` clean.
