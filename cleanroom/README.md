# cleanroom — Autoresearch System

A frozen-contract scaffold for the self-optimizing data-agent. The loop proposes
a change, gates it through a frozen pore, applies it, measures objectively, and
keeps or discards. It also generalises beyond Postgres — the same loop drives
three additional domain benchmarks (kernel, quant, bio) via injected adapters.

## Package Layout

```
cleanroom/
├── types.py                    # REAL: Candidate, Result, PoreResult (frozen contract)
├── db/
│   ├── __init__.py
│   └── schema.sql              # REAL: PostgreSQL schema (frozen)
├── logclient/                  # Story B, issue #3 — production Postgres LogClient
│   └── __init__.py             # LogClient protocol (stub until B ships)
├── benchmark/                  # Story B, issue #3 — real Aiven Postgres harness
│   └── __init__.py             # run_benchmark, check_correctness, is_within_noise
├── pore/                       # Story B, issue #3 — frozen rule-based risk gate
│   └── __init__.py             # evaluate() — never self-tunes (C depends on this)
├── loop/                       # Story A, issue #2 — main orchestration (REAL)
│   ├── __init__.py             # run_loop(task_spec, *, proposer, benchmark, pore,
│   │                           #          logclient, actions=None, iterations=10)
│   └── proposers.py            # ClaudeProposer (API), ClaudeCodeProposer (container)
├── actions/                    # Story A, issue #2 — index/GUC apply + rollback (REAL)
│   └── __init__.py             # apply(), rollback() — CREATE/DROP INDEX, ALTER SYSTEM
├── boundary/                   # Story C, issue #4 — escalation analysis (REAL)
│   └── __init__.py             # escalation_rate_by_drift(), escalations_per_unit_work()
├── dashboard/                  # Story C, issue #4 — ASCII proprioception view (REAL)
│   └── __init__.py             # render(logclient, task_id) -> str
├── modelaxis/                  # Story C, issue #4 — model cost/autonomy axis (REAL)
│   └── __init__.py             # region_per_dollar() -> list[dict]
├── domains/                    # Epic #8, issues #9–11 — domain benchmarks (REAL)
│   ├── kernel/                 # #9: matrix-multiply timing judge (pure Python)
│   ├── quant/                  # #10: walk-forward OOS Sharpe judge (pure Python)
│   └── bio/                    # #11: held-out F1 judge, logistic regression (pure Python)
├── integration/                # Phase 3 wiring (REAL) — C ← B's real Postgres log
│   └── __init__.py             # PoreModuleAdapter, connect_logclient, seed_if_empty,
│                               # run_model_axis_comparison, live_dashboard
└── fixtures/                   # Zero-infra testing harness (REAL)
    ├── __init__.py             # CannedBenchmark, NoOpPore, InMemoryLogClient, DummyProposer
    └── seed_synthetic_log.py   # Synthetic log seeder — builds boundary curves before A/B land
```

## Ownership & Story Mapping

| Component | Story | Issue | Status |
|-----------|-------|-------|--------|
| `types.py` | — | — | REAL (frozen) |
| `db/schema.sql` | — | — | REAL (frozen) |
| `loop/`, `actions/` | A | #2 | REAL |
| `benchmark/`, `pore/`, `logclient/` | B | #3 | REAL |
| `boundary/`, `dashboard/`, `modelaxis/`, `fixtures/seed_synthetic_log.py` | C | #4 | REAL (Phase 0 + Phase 3) |
| `integration/` | C+B | #4/#3 | REAL — Phase 3 wiring (C ← B's PgLogClient) |
| `domains/kernel/` | Epic | #9 | REAL |
| `domains/quant/` | Epic | #10 | REAL |
| `domains/bio/` | Epic | #11 | REAL |
| `fixtures/{CannedBenchmark, NoOpPore, InMemoryLogClient, DummyProposer}` | — | — | REAL (runnable) |

## Contract Rules

1. **Frozen signatures:** Function signatures in each module are locked. Do not add, remove, or rename parameters without co-author consensus (all three stories).

2. **Stubs raise NotImplementedError:** Every production symbol owned by a story body raises `NotImplementedError("<symbol> — owned by Story <X>, GitHub issue #<N>")`. This makes ownership crystal clear in tracebacks.

3. **Fixtures are real:** The `fixtures/` module provides working implementations of all protocols and key functions so Stories A and C can build and test end-to-end against zero infrastructure.

4. **Types are immutable:** Use `@dataclass(frozen=True, slots=True)` for all contract types.

---

## Story C — Boundary Dashboard (issue #4)

Measures where the agent's autonomy boundary is and makes the manifesto's bet visible.

### What it builds

**`boundary/`** — two escalation curves:
- `escalation_rate_by_drift(logclient)` — spatial curve: escalation rate grouped by `drift_level`. Shows where the edge is *right now*. Labelled as a **proxy / lower-bound** — the frozen pore gates blast-radius risk, not the agent's true epistemic edge.
- `escalations_per_unit_work(logclient)` — longitudinal curve: escalation ratio bucketed by cumulative experiment count. With the frozen pore this is **flat by design** — the pore doesn't learn. That flat line is the demo beat: *"the frontier does not yet recede; the amortized membrane is the bet to bend it down."*

**`dashboard/`** — `render(logclient, task_id)` — ASCII text dashboard showing all three panels with honest labels.

**`modelaxis/`** — `region_per_dollar(logclient)` — autonomous experiments per dollar per model. Two cells (haiku vs sonnet) prove the axis is measurable.

**`fixtures/seed_synthetic_log.py`** — populates `InMemoryLogClient` with synthetic experiments across drift levels 0→1.0 and a cumulative volume timeline. Enables Phase 0 fully independently of A and B.

### Phase status

- **Phase 0 (done):** all four modules implemented and running on synthetic data.
- **Phase 3 (done):** `cleanroom/integration/` wires C to B's real `PgLogClient`.
  Integration #2 — C reads from the live Postgres log; integration #3 — model axis
  runs via `run_model_axis_comparison` (swap `DummyProposer` → `ClaudeProposer` once
  `ANTHROPIC_API_KEY` is available).

### Run the dashboard

Phase 0 — synthetic data, no infra:
```bash
cd SunsteadHack
PYTHONPATH=. python3 cleanroom/fixtures/seed_synthetic_log.py
```

Phase 3 — live Aiven Postgres:
```bash
cd SunsteadHack
export CLEANROOM_PG_DSN="postgres://..."
.venv/bin/python3 -m cleanroom.integration   # seeds if empty, renders live dashboard
```

Phase 3 integration tests:
```bash
CLEANROOM_PG_DSN="postgres://..." .venv/bin/python3 tests/test_phase3.py
```

---

## Epic #8 — Domain Benchmarks (issues #9–11)

Proves the autoresearch substrate generalises beyond Postgres by plugging three
different frozen judges into the **same** `run_loop` via the injected `actions=`
parameter. Nothing changes in the loop itself — only the benchmark, actions
adapter, and pore differ per domain.

### The objective-mapping rule

Every domain maps its loss onto `Result.p99_ms` (lower = better) and its hard
constraints onto `check_correctness`. The loop minimises `p99_ms` and gates on
correctness — we do not add fields to `Result`.

| Domain | `p99_ms` | `check_correctness` |
|--------|----------|---------------------|
| Kernel | wall-clock latency (ms) — native fit | `allclose` vs frozen reference output |
| Quant  | `−Sharpe` on OOS window | no lookahead, costs applied, position limits |
| Bio    | `1 − F1` on held-out test set | valid output schema, no test-label access |

### How to inject a domain into `run_loop`

```python
from cleanroom.loop import run_loop
from cleanroom.fixtures import InMemoryLogClient
from cleanroom.domains.kernel import KernelBenchmark, KernelActions, KernelPore, KernelProposer, KERNELS

env = {"kernel_fn": KERNELS["naive"], "_cur_strategy": "naive"}
run_loop(
    task_spec={"task_id": "kernel-demo", "model": "test", "conn": env},
    proposer=KernelProposer(),
    benchmark=KernelBenchmark(),
    pore=KernelPore(),
    logclient=InMemoryLogClient(),
    actions=KernelActions(),   # ← injected adapter; default is Postgres index/GUC
    iterations=6,
)
```

The same pattern works for `quant` and `bio` — just swap the imports.

### Kernel (issue #9)

**File:** `cleanroom/domains/kernel/__init__.py`

32×32 pure-Python matrix multiply. Four variants:

| Strategy | Description |
|----------|-------------|
| `naive` | `i,j,k` order — many cold B-column accesses; the slow baseline |
| `row_order` | `i,k,j` with hoisted `A[i][k]` — saves one list lookup per inner `j` |
| `tiled_8` | Blocked 8×8 tiles — better cache locality |
| `comprehension` | Transposed B + `sum()` generator — typically fastest in CPython |

`check_correctness` runs `allclose(output, reference_out)` first. A kernel that is fast but numerically wrong is **structurally never kept** — the proposer cannot fake speed without correctness.

`KernelPore` escalates out-of-bound tile sizes and unknown strategy names.

`KernelProposer` cycles through variants for testing (no Claude API needed).

### Quant (issue #10)

**File:** `cleanroom/domains/quant/__init__.py`

Momentum strategy on 1 000-day synthetic OHLCV data (geometric Brownian motion, seeded). Walk-forward: 700 days in-sample / 300 days OOS split into 3 folds.

- `p99_ms = −mean_fold_Sharpe` (lower = better OOS Sharpe)
- `samples` = per-fold OOS Sharpe (3 values) for noise detection
- `check_correctness` rejects `lookback ≤ 0` (lookahead) and `threshold < 0`
- `is_within_noise` uses a **≥ 0.2 Sharpe practical threshold** — cross-fold stdev on 100-day windows is ~2+, making statistical tests useless; domain practice requires ≥ 0.2 to be taken seriously

`QuantPore` escalates negative lookback and degenerate params.

`QuantProposer` cycles through lookback/threshold combos for testing.

### Bio (issue #11)

**File:** `cleanroom/domains/bio/__init__.py`

Molecular property classification: 200-sample synthetic tabular dataset (8 features, binary label, true signal in first 3 features). Split: 60% train / 20% dev / 20% test (held-out, never exposed to proposer).

Pure-Python logistic regression (gradient descent, no scipy/sklearn). Pipeline hyperparams: `lr`, `max_iter`, `threshold`, `l2`.

- `p99_ms = 1 − F1` on 2 held-out test shards (lower = better accuracy)
- `check_correctness` rejects `use_test_labels=True` (contamination flag)
- Both the pore and `check_correctness` independently catch the contamination flag — defence in depth

`BioProposer` cycles from a very poor baseline (lr=0.0001, max_iter=1) through progressively better hyperparams, producing a clear descending curve.

### Running the domain tests

```bash
cd SunsteadHack
PYTHONPATH=. python3 tests/test_domains.py
```

10 tests: 3 e2e loop runs (one per domain), 3 correctness gate checks, 3 pore escalation checks, 1 backward-compat check. No external dependencies.

---

## Quick Start (Postgres loop)

```python
from cleanroom.fixtures import CannedBenchmark, NoOpPore, InMemoryLogClient, DummyProposer
from cleanroom.loop import run_loop

run_loop(
    task_spec={"task_id": "test", "model": "dummy", "conn": None},
    proposer=DummyProposer(),
    benchmark=CannedBenchmark(baseline_p99=100.0),
    pore=NoOpPore(),
    logclient=InMemoryLogClient(),
    iterations=5,
)
```

## Installation

```bash
pip install -e .
```

## Smoke Test

```bash
python3 -c "from cleanroom.fixtures import CannedBenchmark, NoOpPore, InMemoryLogClient, DummyProposer; print('ok')"
```
