# Green-bond data-quality agent

An agent that searches the extracted green-bond dataset for data-quality issues,
**corrects** the ones that are objectively determined, **flags** the ones a human
should judge, and **escalates** the ones only the source PDF can settle — with a
one-line reason for each.

> The CSVs are *extracted* from messy PDFs. "The only truth is the PDFs," and we
> don't have them — so the agent reasons over the extracted values **and the
> `*_source_trail` text that narrates how each value was derived**, and abstains
> (escalates) where the data alone can't resolve it. A confident-wrong
> auto-correction is the dangerous failure here, so the agent errs toward asking.

## Run

No API key needed for the deterministic tiers:

```bash
cd arctal_dq_agent
python -m agent                 # Tier 0 + trail re-derivation -> out/{findings.jsonl,REPORT.md}
```

Add the LLM reasoning tier (needs `anthropic` + `ANTHROPIC_API_KEY`):

```bash
pip install anthropic           # or: uv pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python -m agent --llm
```

Runs in ~0.02s on the 100-bond sample. Data dir defaults to
`../2026-06-23_100-bond-sample-takehome`; override with `BONDS_DATA_DIR`.
Example output is checked in under [`examples/`](examples/).

Tests: `uv pip install pytest && python -m pytest` (14 unit tests on the
deterministic checks and the trail re-derivation).

## What it checks, and why it's not just SQL

The system is three tiers. The point of the split is **cost** (run the cheap thing
on everything, the expensive thing only where it's needed) and **trust** (be
explicit about which findings are arithmetic facts vs. judgments).

### Tier 0 — deterministic re-derivation (every row, ~free, scales to 30k)
Recompute each value from its primitives and check it reconciles. These are exact,
cheap, and the necessary foundation — but *not* where an agent earns its keep.
`per_million`, `coverage`, `alloc_recon`, `cat_usd_sum`, `share_def`,
`category_count`, `fx_consensus`, `date_sanity`, `duplicate_isin`
(see [`agent/checks.py`](agent/checks.py) — each has a one-line spec in the module
docstring). On this sample most of these **pass**: the pipeline does its own
arithmetic correctly, which is exactly why a clean *failure* is a strong signal.
The ones that do fire are the cross-row ones a single-row check misses —
`fx_consensus` flags 16 bonds whose implied FX rate disagrees with how the rest of
the corpus converts that currency.

### Tier 0.5 — source-trail re-derivation (the flagship "beyond SQL" check)
Every impact value ships a `source_trail` that *narrates its own derivation* in
free text, e.g.
`"53,044.00 MWh × bond_share 0.180000 = 9,547.92 MWh; 9,547.92 / 1,170.6M USD = 8.16 MWh/$M"`.
[`agent/trail.py`](agent/trail.py) parses that prose, re-derives the arithmetic, and
**cross-checks it against the stored numbers**. The high-value catch:

> Bond `BE0000346552` stores an `impact_value` of **989,000,000 MWh**, but its own
> trail derives **989,000**. A pure per-million check passes (the intensity was
> recomputed from the inflated value), so SQL never sees it — only reading the
> narration does. It's a 1000× error, and it lines up with that row's "PMU exceeds
> cap" note.

205 of 240 sample trails carry this re-derivable arithmetic, so this is a
high-coverage surface, not a one-off.

### Tier 1 — LLM reasoning (only the residual Tier-0 can't reach)
Two deep judgments that have no arithmetic ground truth (`--llm`,
[`agent/reasoning.py`](agent/reasoning.py)):
- **impact plausibility** — is the value/unit physically sane for a bond this size
  (a tCO2e↔ktCO2e mislabel is ~1000× off), judged against per-metric peers and the
  trail's provenance.
- **category-mapping plausibility** — does the reported text / subcategory
  description actually fit the assigned ICMA category, or is it misattributed?

Tier 1 only runs on rows a **free deterministic triage** selects (intensity
outliers vs. peers, pipeline `review_notes` present, or a trail with no
re-derivable arithmetic) — 22% of rows on this sample. A cheap model (Haiku) does
the first pass; only low-confidence cases escalate to a stronger model (Sonnet).

### Tier 2 — disposition (the located-autonomy decision)
Every finding gets exactly one disposition:
- **`auto_correct`** — the fix is objectively determined (a recomputed number). The
  corrected value ships in `proposed_correction` with its evidence.
- **`flag`** — a real inconsistency whose *fix* is debatable → human triage.
- **`escalate`** — genuinely ambiguous / only the PDF resolves it → the agent
  **abstains** and points at what to open. Never a silent auto-correct.

The `data_quality_flags` / `review_notes` columns are the pipeline's own output;
we treat them as **triage hints, not targets** — we never try to reproduce or
"clear" them, we add the *why*.

## Two output channels (a deliberate split)

You use AI to trawl logs; a domain expert triages findings. So the output is split
on purpose:
- **`findings.jsonl`** — one finding per line, full evidence (conflicting values,
  trail excerpts, proposed corrections). For your tools to consume.
- **`REPORT.md`** — ranked, grouped by disposition, **one line of *why* per
  finding**, with rollup counts. A non-engineer triages it in minutes. The numbers
  live in the JSONL so this page never becomes a wall of text.

Sample run (deterministic mode, no key): **255 findings over 1,062 rows** —
3 auto-correct, 17 flag, 235 escalate. The 235 escalations are the no-LLM agent
**abstaining** on the semantically-hard rows rather than clearing them; turn on
`--llm` and those become resolved ok/flag/escalate judgments.

## Cost / performance at 30k+

The funnel *is* the cost story:
- **Tier 0 + trail** is pure Python over `csv` — **1,062 rows in ~0.02s, $0**.
  Linear; ~0.6s and $0 for 30k. This is the floor, and it runs on everything.
- **Tier 1** only touches the triaged residual (**22% of rows** here) and tries the
  cheap model first, so spend scales with *ambiguity*, not row count. Every call is
  counted and the per-bond cost is printed at the end of a run, so the 30k figure is
  **measured on the sample and extrapolated**, not guessed. (Run `--llm` to fill in
  the measured number; with no key the agent stays in the $0 deterministic tiers.)
- Further levers for the real corpus: cache by `(field, source_trail hash)` so
  identical trails are reasoned once; batch the Tier-1 calls.

## Honest limits

- **No PDFs.** Tier 1 reasons over extracted data + `source_trail` only. Where that
  isn't enough it escalates *with* the cited `source.arctal.ai` document — it does
  not pretend to verify against the primary source.
- The deterministic tiers are exact; **Tier 1 is heuristic and labelled as such**
  (every LLM finding carries `tier: "llm"` and a confidence). Treat its `flag`s as
  leads, not verdicts.
- `fx_consensus` uses a corpus-derived median rate, so it's blind to a *correct*
  off-consensus rate (a genuinely unusual placement date); hence `flag`, never
  auto-correct.

## What I'd do next

- Resolve the `escalate` queue against the cited PDFs (fetch + verify), turning a
  chunk of escalations into auto-corrections.
- Promote `cat_usd_sum` and the trail bond-share step from per-row to a reconciled
  per-ISIN view once duplicate-ISIN handling matters at scale.
- A small human-audited gold set to calibrate Tier-1 confidence thresholds.

## For benchmarking / pipeline integration

The per-record decision is exposed as a clean, I/O-free function
([`agent/review.py`](agent/review.py)):

```python
from agent import review            # review(record) -> Decision
d = review(row)                     # Decision(verdict ∈ {"ok","error","escalate"}, confidence, rationale)
```

`ok` = stands behind the value, `error` = a data-quality issue, `escalate` = needs a
human. `assess_record(table, row, ctx, reasoner)` is the underlying pure seam that
returns the full `Finding` list. This is the only surface a benchmark or the main
pipeline needs to wrap — it has no dependency on the CLI or the reporting code.
