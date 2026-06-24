# SunsteadHack — Self-Optimizing Data-Agent

An autonomous research workflow with one defining move: **it knows when to stop.** It runs
[Karpathy `autoresearch`](https://github.com/karpathy/autoresearch)'s "modify → run →
measure → keep-or-discard → repeat" loop — but on a **live database** instead of a training
script. The objective database metric (p99 latency / cost / throughput) plays the role of
autoresearch's `val_bpb`: it's the judge, so there's no human in the loop per experiment. At
the edge of what it can stand behind, it stops and escalates to a human — and that boundary
is drawn live and measured.

> **Read first:** the [manifesto](docs/manifesto.md) — the thesis, the bet, and what ships
> vs. what we're betting on.

Aiven project: `konsta-sunsteadhack` (cloud `google-europe-north1`).

---

## Why this framing is legitimate

`autoresearch` works because it has an objective, cheap, hard-to-game metric — so it needs
zero human review between experiments. Most enterprise work *lacks* such a metric ("is this
PR good?") and stays human-gated. **Database performance is one of the rare domains that
already has a real objective metric**, so we can close the autonomous loop honestly, today,
on the Aiven MCP surface. Where a change has blast-radius or isn't reversible, a frozen
rule-based *pore* stops and asks a human — and the rate at which that happens, plotted
against workload drift and cumulative volume, *is* the instrument.

See [`docs/aiven_agentic_org.md`](docs/aiven_agentic_org.md) and the architecture diagram
[`docs/aiven-architecture.png`](docs/aiven-architecture.png).

## The `cleanroom/` system

The build lives in the [`cleanroom/`](cleanroom/) package — a frozen-contract scaffold so
three teammates can build in parallel. Real & frozen: the contract types
([`cleanroom/types.py`](cleanroom/types.py)) and the escalation-log schema
([`cleanroom/db/schema.sql`](cleanroom/db/schema.sql)). Runnable with zero infra: the
[`fixtures/`](cleanroom/fixtures/) (canned benchmark, no-op pore, in-memory log client, dummy
proposer). See [`cleanroom/README.md`](cleanroom/README.md) for the full layout and contracts.

```bash
pip install -e .
python -c "from cleanroom.fixtures import CannedBenchmark, NoOpPore, InMemoryLogClient, DummyProposer; print('ok')"
```

### Work split (async, contract-bound)

| Story | Owner | Package | Issue |
|---|---|---|---|
| **A — Interior loop** (autoresearch engine) | Me | `loop/`, `actions/` | [#2](https://github.com/PlayerPlanet/SunsteadHack/issues/2) |
| **B — Substrate** (benchmark, pore, log client) | Noel | `benchmark/`, `pore/`, `logclient/`, `db/` | [#3](https://github.com/PlayerPlanet/SunsteadHack/issues/3) |
| **C — Boundary instrument** (curves, dashboard, model axis) | Mikael | `boundary/`, `dashboard/`, `modelaxis/` | [#4](https://github.com/PlayerPlanet/SunsteadHack/issues/4) |

## Build status

- ✅ **Phase-0 skeleton landed** (`cleanroom/` — frozen types + schema + runnable fixtures).
  Stories A and C can import real symbols and build against fixtures today.
- ✅ **Gate 1 (freezable workload) + Gate 2 (signal beats noise): PASS** — measured noise
  floor ≈ CV 6.5 % on the live `sunstead-pg-bench` service. See
  [`docs/gate-1-findings.md`](docs/gate-1-findings.md).
- ⚠️ **`hypopg` is unavailable** on our Aiven plan → index discovery uses real
  `CREATE INDEX` / `DROP INDEX` on a small dataset (reversible). Propagated to issue #2.
- ⏳ **Still open:** MCP write-tool rate limits, live cost read, real-workload choice
  (pgbench vs JOB).

## Membrane governance probe (precursor / fallback)

The repo also carries the original **membrane-crossing probe** — the governance pattern the
clean-room pore generalizes (a frozen, rule-based gate that stops and asks a human on
high-risk crossings). It's also the **fallback direction** if the objective-loop gates fail.
It monitors clinical-claim and model/calibration surfaces, suggests regulated crossing pores,
and logs human judgments to an append-only escalation log.

```bash
# Run the membrane probe
python scripts/stage_membrane_unit.py --actor agent-builder-001 --output artifacts/staged-unit.json

# Record a human judgment
python scripts/record_judgment.py --input artifacts/staged-unit.json \
  --decision modify --pore regulatory_clinical_safety --judge human-regulatory-001 \
  --rationale "Clinical claim too strong for patient-facing copy." \
  --transform "Rewrite to: estimates personalized migraine-related work-disruption risk."
```

| Cell | Risk | Pore |
|---|---|---|
| `clinical-claims-surface` | HIGH | `regulatory_clinical_safety` |
| `migraine-risk-core` | MEDIUM | `model_transparency` |
| `operator-playbooks` | LOW | `public_benign` |

Probe runs always exit 0 (risk flags are recorded in JSON, not raised); the escalation log
(`cells/agent-escalation-log/crossings.yaml`) is append-only; the probe and webhook receiver
use only the Python standard library. See [`docs/membrane-trial.md`](docs/membrane-trial.md)
and [`docs/homeserver-deployment.md`](docs/homeserver-deployment.md).

## Repository map

| Path | Purpose |
|---|---|
| [`cleanroom/`](cleanroom/) | The self-optimizing data-agent (front-runner build) |
| [`docs/manifesto.md`](docs/manifesto.md) | The thesis: it knows when to stop |
| [`docs/aiven_agentic_org.md`](docs/aiven_agentic_org.md) | Clean-room / located-autonomy strategy brief |
| [`docs/solution-directions.md`](docs/solution-directions.md) | Team context: directions, gates, on-site questions |
| [`docs/gate-1-findings.md`](docs/gate-1-findings.md) | Verified Aiven infra facts (freezability, extensions, GUCs) |
| `cells/`, `scripts/`, `deploy/` | Membrane-crossing probe (governance precursor / fallback) |
