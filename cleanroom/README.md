# cleanroom — Phase-0 Autoresearch System

A frozen-contract scaffolding for three parallel stories building the cleanroom autoresearch loop.

## Package Layout

```
cleanroom/
├── types.py                    # REAL: Candidate, Result, PoreResult (frozen contract)
├── db/
│   ├── __init__.py
│   └── schema.sql              # REAL: PostgreSQL schema (frozen)
├── logclient/                  # STUB: Story B, issue #3 (production logging)
│   └── __init__.py             # LogClient protocol + NotImplementedError stubs
├── benchmark/                  # STUB: Story B, issue #3
│   └── __init__.py             # run_benchmark, check_correctness, is_within_noise
├── pore/                       # STUB: Story B, issue #3 (risk evaluation)
│   └── __init__.py             # evaluate() — frozen, rule-based
├── loop/                       # STUB: Story A, issue #2 (main orchestration)
│   └── __init__.py             # run_loop(task_spec, ...)
├── actions/                    # STUB: Story A, issue #2
│   └── __init__.py             # apply(), rollback() — index discovery via hypopg
├── boundary/                   # STUB: Story C, issue #4 (escalation analysis)
│   └── __init__.py             # escalation_rate_by_drift(), escalations_per_unit_work()
├── dashboard/                  # STUB: Story C, issue #4
│   └── __init__.py             # render(logclient, task_id) -> HTML/text
├── modelaxis/                  # STUB: Story C, issue #4
│   └── __init__.py             # region_per_dollar() — cost/confidence tradeoff
└── fixtures/                   # REAL: Zero-infra testing harness
    ├── __init__.py             # CannedBenchmark, NoOpPore, InMemoryLogClient, DummyProposer
    └── seed_synthetic_log.py   # STUB: Story C, issue #4 (populate dummy data)
```

## Ownership & Story Mapping

| Component | Story | Issue | Status |
|-----------|-------|-------|--------|
| `types.py` | — | — | REAL (frozen) |
| `db/schema.sql` | — | — | REAL (frozen) |
| `loop/`, `actions/` | A | #2 | STUB |
| `benchmark/`, `pore/`, `logclient/`, `db/` | B | #3 | STUB |
| `boundary/`, `dashboard/`, `modelaxis/`, `fixtures/seed_synthetic_log.py` | C | #4 | STUB |
| `fixtures/{CannedBenchmark, NoOpPore, InMemoryLogClient, DummyProposer}` | — | — | REAL (runnable) |

## Contract Rules

1. **Frozen signatures:** Function signatures in each module are locked. Do not add, remove, or rename parameters without co-author consensus (all three stories).

2. **Stubs raise NotImplementedError:** Every production symbol owned by a story body raises `NotImplementedError("<symbol> — owned by Story <X>, GitHub issue #<N>")`. This makes ownership crystal clear in tracebacks.

3. **Fixtures are real:** The `fixtures/` module provides working implementations of all protocols and key functions so Stories A and C can build and test end-to-end against zero infrastructure.

4. **Types are immutable:** Use `@dataclass(frozen=True, slots=True)` for all contract types.

## Quick Start

Import and use the fixtures for Phase-0 testing:

```python
from cleanroom.fixtures import (
    CannedBenchmark,
    NoOpPore,
    InMemoryLogClient,
    DummyProposer,
)
from cleanroom.types import Candidate, Result, PoreResult

# Initialize
benchmark = CannedBenchmark(baseline_p99=100.0)
pore = NoOpPore()
logclient = InMemoryLogClient()
proposer = DummyProposer()

# Run a mini loop (Story A will wire this into run_loop())
candidates = []
for i in range(5):
    candidate = proposer.propose({"task_id": "test"}, candidates)
    pore_result = pore.evaluate(candidate)
    result = benchmark.run_benchmark(None, "test_workload")
    logclient.write_experiment(
        task_id="test",
        model="dummy",
        drift_level=0.0,
        candidate=candidate.__dict__,
        baseline_p99=100.0,
        candidate_p99=result.p99_ms,
        cost_estimate=result.cost_estimate,
        correctness_ok=True,
        within_noise=False,
        decision="keep" if i < 3 else "discard",
    )
    candidates.append(candidate)

# Read back
experiments = logclient.read_experiments()
for exp in experiments:
    print(f"  Iteration {exp['id']}: p99={exp['candidate_p99']:.1f}ms")
```

## Installation

```bash
pip install -e .
```

## Smoke Test

```bash
python -c "from cleanroom.fixtures import CannedBenchmark, NoOpPore, InMemoryLogClient, DummyProposer; from cleanroom.types import Candidate, Result, PoreResult; print('✓ All imports successful')"
```
