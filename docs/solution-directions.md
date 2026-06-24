# SunsteadHack — Solution Directions & Context

> Shared context for the team. Captures the candidate directions we've scoped, the
> front-runner, the gates that tell us when to pivot, and the questions to get answered
> on site. Living doc — edit freely.

Aiven project: `konsta-sunsteadhack` (cloud `google-europe-north1`).

## TL;DR

We're building a **self-optimizing Data-Agent**: an AI agent that runs Karpathy
[`autoresearch`](https://github.com/karpathy/autoresearch)'s "modify → run → measure →
keep-or-discard → repeat" loop, but on a **live database** instead of a training script.
The objective database metric (p99 latency / cost / throughput) plays the role of
autoresearch's `val_bpb` — it's the judge. That objective metric is what makes the whole
framing legitimate: no human in the loop per experiment, no soft/gameable scoring.

## Why this is the front-runner

`autoresearch` works because it has an objective, cheap, hard-to-game metric (`val_bpb`)
— so it needs zero human review between experiments. Most enterprise work *lacks* such a
metric (e.g. "is this PR good?") and stays human-gated, which doesn't scale. **Database
performance is one of the rare domains that already has a real objective metric.** So we
can close the autonomous loop honestly here, today, on the Aiven MCP surface we already
have connected.

## The loop

| autoresearch | self-optimizing Data-Agent |
|---|---|
| `program.md` (direction) | "minimize p99 on workload X, cost ≤ budget" |
| `train.py` (modifiable surface) | indexes, Postgres GUCs, PgBouncer pool sizing, query rewrites, partitioning (optionally Kafka topic config) |
| 5-min training run | apply change → run **fixed benchmark** → measure |
| `val_bpb` (the judge) | p99 latency / throughput / cost-per-query / cache-hit ratio |
| keep-or-discard | keep if metric improved **and** no guardrail regression; else roll back |

**Aiven MCP tools that enable it:** `aiven_pg_service_query_statistics` +
`aiven_service_metrics_fetch` (metric); `aiven_pg_optimize_query`, `aiven_pg_read`,
`aiven_pg_write`, `aiven_service_update`, `aiven_pg_bouncer_update` (actions);
`aiven_service_plan_pricing` (cost); `aiven_pg_service_available_extensions`
(`hypopg`, `pg_stat_statements`).

**Demo:** a descending p99 curve over the experiment loop, cost held flat, correctness
preserved, plus an experiment log — e.g. *"kept: composite index on (user_id, created_at),
−38% p99; discarded: work_mem bump, within noise."* A Karpathy-style improvement chart,
but the artifact being optimized is a live production database.

## Make-or-fail gates (when to pivot)

Each gate is a precondition for the objective loop. If one fails, we change approach
rather than push a loop that's silently broken.

1. **Fixed benchmark exists.** Can we capture/replay `pg_stat_statements` as an immutable,
   representative workload? If we can't get a stable comparable workload → the metric lies
   → **pivot**.
2. **Signal beats noise.** Warmup + multiple trials + significance test. If gains sit
   within measurement variance → the loop chases noise → change the action space or pivot.
3. **Cheap-reversible action space + proxy.** Fast apply/rollback of index/GUC/pool
   changes; `hypopg` + `EXPLAIN` to evaluate hypothetical indexes *without* building them.
   If everything needs a restart/migration → loop too slow → fewer/bigger experiments or
   pivot.
4. **Correctness equivalence checkable.** A query rewrite/index must not change results, or
   we can't safely auto-keep a change.
5. **Multi-objective constraint holds.** Cost stays bounded while latency drops (no cheating
   by bumping to a giant plan). If we can't constrain → fall back to single-objective at a
   fixed plan.
6. **Time-box fallback.** If there's no descending curve by demo-midpoint, ship a scripted
   single-optimization demo (one slow query → `hypopg`-suggested index → measured win)
   instead of the full loop.

## Questions to get answered on site

**Aiven engineers**
- Is there a sandbox/throwaway service we can hammer with a benchmark, or must we tune a
  shared/prod service? (need isolation for clean measurement)
- Rate limits/quotas on write tools (`service_update`, `pg_write`) — how fast can the loop
  iterate?
- Do GUC changes require a restart, or apply live? Which params are dynamic?
- Are `hypopg` + `pg_stat_statements` available on our plan?
- Metric resolution/latency from `aiven_service_metrics_fetch` — granular enough to score a
  ~5-min experiment?
- Can we pull `pg_stat_statements` history to build the replay benchmark?
- Does `aiven_service_connection_info` give a direct connection for our own benchmark
  harness?
- How is projected cost surfaced so we can enforce the budget constraint live?

**Challenge owners / judges**
- Judging weighting: novelty vs working demo vs business value?
- Aiven-specific prize track vs cross-cutting? Are AWS / Tangled also sponsors (do they
  score)?
- Preferred dataset/workload, or bring our own? Demo slot length? Any constraints on
  touching live infra during the demo?

## Fallback directions (if the objective-loop gates fail)

- **Data-Agent + membrane governance.** Agent provisions/tunes infra; every mutation stages
  → crosses a *pore* (schema-compat, cost-envelope, blast-radius); HIGH-risk needs human
  judgment; all logged. Reuses the existing membrane-crossing probe. Spine = provisioning
  demo (intent → live infra). See `docs/membrane-trial.md`.
- **Tangled ATProto explainability.** Custom lexicons (`com.sunstead.crossing` /
  `com.sunstead.judgment`) as signed PDS records; alternative appviews = a plural
  explainability layer. *Confirmed feasible:* Tangled stores `sh.tangled.*` records in PDSes
  over the public firehose, custom lexicons coexist, and anyone can build an alternative
  appview. Caveats: writes need user OAuth; git contents + (knot v1.15+) collaborator data
  are knot-XRPC, not firehose; network-wide discovery needs a Jetstream consumer.
- **v2 amortized judge.** Learn human judgement on *stationary* surfaces from the signed
  judgment corpus → generalizes autoresearch beyond objective-metric tasks. Soft/gameable
  (Goodhart) — only safe with calibrated abstention + drift detection + a trust ladder.
  Deferred until we have the objective loop working.

## Next build step

Spec the loop architecture (benchmark harness, action space, keep/discard + rollback,
constraint handling) and the eval rigor (fixed-workload capture, warmup/trials/significance,
train/test split). **Start Postgres-only**; add Kafka tuning later if desired.
