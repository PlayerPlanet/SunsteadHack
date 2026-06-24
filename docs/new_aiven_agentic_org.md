# SunsteadHack — Solution Directions & Context

> Shared context for the team (and other agents working on this repo). Captures the
> current synthesis, the architecture, the critical framing discipline, and the
> gates that tell us when to pivot. Living doc — edit freely.

Aiven project: `konsta-sunsteadhack` (cloud `google-europe-north1`).

## TL;DR

Not "autonomous DB tuning." We're building **located autonomy, instrumented**: an
autonomous workflow that acts without human approval only where it can *prove* it's
safe to — objective, stationary reward + cheap-reversible action — and explicitly
escalates everywhere else. The deliverable isn't "fewer humans." It's a measured,
falsifiable answer to "exactly how far does the safe region extend right now, with
this agent" — including an honest answer for where it doesn't extend yet.

This generalizes Karpathy's [`autoresearch`](https://github.com/karpathy/autoresearch)
("modify → run → measure → keep-or-discard → repeat", judged by an objective metric)
from a training script to live data infrastructure via the Aiven MCP. Aiven plays two
roles at once: the **substrate** the agent swarm runs on (Kafka for agent-to-agent
comms, Postgres+pgvector for memory) and the **target** being autonomously tuned
(Postgres primarily, Kafka secondarily). The DB-tuning loop is no longer the headline
— it's one proof-of-stationary-autonomy pod inside a bigger instrument that also
measures its own boundary.

## Why this is the front-runner

- Database/infra performance is one of the rare domains with an objective, cheap,
  hard-to-game metric (p99/throughput/cost) — so the interior loop can close honestly
  with zero human review per experiment, same as `val_bpb` does for autoresearch.
- **Verified against real prior art** (web search, 2026-06-24): Datadog uses
  autoresearch internally to improve their SQL-optimization *recommender* — but only
  offline, against synthetic data in a fresh replica, judged by an LLM
  (precision/recall/F1: 0.54→0.86 over 23 experiments), and ships a PR for a human to
  merge. They explicitly do not give it live database write access. That's the precise
  wedge: we do live write access + an objective system metric (not an LLM judge) + a
  closed loop with no human per step, inside a region we can prove is safe. Sources:
  [Datadog autoresearch post](https://www.datadoghq.com/blog/llm-experimentation-autoresearch/),
  [Bits Database Optimization](https://www.datadoghq.com/blog/bits-database-optimization/),
  [docs](https://docs.datadoghq.com/database_monitoring/bits_database_optimization/).
- Generalizing the target away from data infra entirely (ML training, a generic
  "research agent for an org") was considered and rejected: it makes Aiven incidental
  (just a memory/queue backend) instead of load-bearing, which doesn't fit a challenge
  that specifically wants agents that control/stream/query Aiven's data infrastructure.
- Aiven's own single-shot "SQL query optimizer" tool is open-loop advice (a human
  decides whether to apply it). What we're building is closed-loop autonomous action
  with measured proof. Different category, not a bigger version of the same thing.

## Architecture: host *and* target

Three agent roles, not one monolithic loop:

- **Orchestrator** — proposes the next experiment, informed by a pgvector similarity
  search over past experiments (don't repeat known-bad attempts). Publishes to Kafka
  (`experiments.proposed`).
- **Worker** — subscribes, applies the action via Aiven MCP tools, runs the fixed
  benchmark. This is **deterministic code, not an LLM call** — translating "add
  composite index on (a,b)" into the actual `CREATE INDEX` and executing it is
  mechanical. Publishes results (`experiments.completed`).
- **Judge** — subscribes to results, applies keep/discard against significance +
  guardrails (cost, correctness). Also **deterministic code, not an LLM call** — this
  is a numeric threshold comparison; an LLM is a worse, less reliable gatekeeper than a
  five-line significance test. Writes the full record to Postgres, publishes the
  decision (`experiments.decided`).

**LLM calls are reserved for strategic judgment only**: proposing the next experiment,
reflecting on why a failed one failed, and (optionally) a lightweight critic/safety-
review step before any action touches live infra. Everything else is real code
wrapping real MCP calls. This keeps token cost bounded *and* keeps the demo about real
infrastructure visibly changing, not agents exchanging chat logs over Kafka (which
alone would be boring, and is what most "agent swarm" demos look like from outside).

Aiven service mapping:

- **Kafka** — agent-to-agent pub/sub (the comms substrate) *and* a secondary tuning
  target (action space below). Reused honestly across both roles.
- **Postgres + pgvector** — working memory (experiment history, embeddings for
  similarity search) *and* the escalation log (see below) — same store, two jobs.
- **Provisioning via MCP** — agents can spin up their own scratch Postgres/Kafka topic
  on demand, which also answers the "do we have an isolated sandbox" question.
- **OpenSearch** — deprioritized. The challenge brief itself flags it "(not 100%)";
  Postgres+pgvector already covers the memory use case with tools already wired
  (`pg_read`/`pg_write`). Don't add a third storage system to a hackathon demo.

## The two-level benchmark

**Level 1 — Interior benchmark** (proves the loop works): a frozen, replayable
workload. Recommended primary: the **Join Order Benchmark (JOB)** — real IMDB data,
purpose-built to break query-optimizer cost models on multi-join correlations (Leis,
"How Good Are Query Optimizers, Really?"), trivially freezable. `pg_stat_statements`
replay is the fallback — more "real," harder to truly freeze (warmup/cache
state/multi-tenant noise).

Action space (5 modifiable surfaces, each with a cheap-reversible proxy):

1. Index discovery — `hypopg` + `EXPLAIN` (hypothetical indexes, no real build).
2. Query rewrite — requires the correctness-equivalence check, or it can't be
   auto-kept.
3. GUC/knob tuning (`work_mem`, `shared_buffers`, `random_page_cost`) — apply live if
   dynamic, flag if restart-required.
4. PgBouncer pool sizing under a concurrency benchmark.
5. Partitioning / Kafka topic config under a streaming workload. **Caution:** Kafka
   partition increases are **not reversible** — restrict the Kafka action space to
   genuinely reversible knobs (`linger.ms`, batch size, compression, retention), not
   partition count.

Judge: objective metric (p99/throughput/cost), keep-if-improved-and-no-guardrail-
regression, else rollback.

**Level 2 — Boundary benchmark** (the actual centerpiece, not Level 1): measure
**escalation rate as a function of distributional drift** from the frozen baseline.
Build a deliberate stationarity gradient — deep-stationary (JOB replay, escalation ≈
0) → captured-real (`pg_stat_statements`, some drift) → drift-injected (deliberately
perturbed workload, escalation should spike) — run the same frozen loop and frozen
escalation-gate across it, plot escalation-rate vs. drift-distance live off the
Postgres log. This curve is the differentiated artifact: an objective, falsifiable
measurement of exactly where the system's autonomy is trustworthy and where it stops
being trustworthy. Keep the distance metric crude and explainable (simple query-shape/
selectivity histogram distance) — not a research project in itself.

**Why the escalation gate (the "pore") must stay frozen during this measurement**: if
it self-tunes, you can't separate "the world drifted" from "we made the gate looser" —
and that reintroduces the exact failure this instrument exists to catch (gate quietly
widening, mistaken for the agent getting smarter).

## Critical framing discipline — read this before pitching or building

This took several passes to land correctly; stating it plainly so it doesn't need
re-deriving:

- **The goal is never "minimize humans" or "prove we can replace humans."** That
  framing creates a direct incentive to loosen the escalation gate rather than improve
  agent competence — a looser gate and a genuinely smarter agent produce the
  *identical* visible metric (fewer escalations) but opposite substance underneath.
- **The tell**: under injected drift, escalation rate going *up* is the system working
  correctly (recognizing it's out of its depth) — not a failure. If "fewer humans" is
  your stated goal, a rising curve under drift looks like failure, which is the wrong
  reaction and a sign the framing has drifted wrong.
- **Don't claim the safe region keeps expanding indefinitely.** Whether the
  drift-tolerance boundary is bounded or unbounded is the deliberately-open question
  for the demo's closing beat (see below) — not a thing to assert as the thesis.
- **What ships in 48h**: Stage 0 (schema'd escalation log) + Stage 1 (autonomous
  interior + a dumb, frozen, rule-based escalation gate: irreversible / high-blast-
  radius / correctness-uncertain → escalate to a human). **Stage 2** (a calibrated,
  OOD-aware learned membrane that could safely auto-decide escalations itself) is
  explicitly **not** shippable in 48h — articulate it as the research bet, never claim
  it as a result. Claiming it inherits the exact failure mode (hyper-competent against
  a metric that quietly stopped being true) the whole instrument is built to catch.
- **A cheap, honest middle step, if time allows**: pgvector similarity-gated
  abstention. Auto-decide only when a new case is close to a cluster of past human-
  *approved* cases; escalate by default whenever it's novel/dissimilar to everything in
  the log. This is structural abstention, not a trained judge — buildable with the
  memory component already in scope, and it's a legitimate (if partial) answer to "can
  the agent use a graph of past human decisions" without the Goodhart risk of actually
  training on/imitating those decisions.

## Positioning

- **Rubric fit** (per team's read of the challenge): Workflow Autonomy (33%) = the
  located-autonomy thesis itself. MCP depth (34%) = structural — each Aiven service is
  a load-bearing organ (Kafka=comms+target, Postgres+pgvector=memory+log+target,
  provisioning=self-scaffolding sandboxes), not decorative breadth for its own sake.
  Creativity & Impact (33%) = the boundary artifact + the bounded/unbounded open
  question.
- **"Arctal but research"** — keep this analogy at the *organizational-structure*
  level only: small builder-operator team + agent fleet + judgment concentrated in
  humans (not eliminated), vs. linear headcount-to-output scaling. Good vision frame.
- **Do not claim** "we prove research scales sub-linearly in researchers needed" as a
  general law. Arctal's version of that claim rests on years of real operating history
  across *growing task variety*; ours is narrower and demonstrated rather than
  asserted: "within a task we've proven stationary, additional volume needs zero
  proportional human review, and we can show, live, exactly how much of the space
  currently qualifies." The narrower, demonstrated claim beats the broader, asserted
  one in front of technical judges — it survives "how do you know this generalizes" in
  a way the broad claim doesn't.
- Even Arctal's own piece doesn't argue for zero humans — "AI agents... cannot be the
  ones standing behind it" is an irreducible human core, concentrated not eliminated.
  Consistent with our framing, not a stretch of it.

## Make-or-fail gates (when to pivot)

1. **Fixed benchmark exists.** JOB is the recommended answer to this gate (see Level
   1). If we can't get a stable comparable workload → the metric lies → **pivot**.
2. **Signal beats noise.** Warmup + multiple trials + significance test.
3. **Cheap-reversible action space + proxy.** Kafka partition count is **not**
   reversible — exclude it from the action space. `hypopg` + `EXPLAIN` to evaluate
   hypothetical indexes without building them.
4. **Correctness equivalence checkable.** A query rewrite/index must not change
   results, or we can't safely auto-keep a change.
5. **Multi-objective constraint holds.** Cost stays bounded while latency drops.
6. **Time-box fallback.** Scripted single-optimization demo if no descending curve by
   the Phase 1 mid-point checkpoint.
7. **(Recursive) The escalation gate itself must stay frozen during Level 2
   measurement.** If the gate self-tunes, the boundary curve is meaningless — see
   Critical framing discipline above.

## Roadmap — 48h, gate-anchored

- **Phase 0 (~6h)**: On-site questions (below) + provision Postgres/Kafka/pgvector +
  build the escalation-log schema (staged unit, full context, which gate, judgment,
  transform, timestamp — enough to compute per-region escalation rate AND
  distributional features later). Gate #1 must resolve before building further.
- **Phase 1 (Day 1 night, ~8–10h)**: single-task interior loop — index discovery on
  JOB, `hypopg`+`EXPLAIN` proxy, fixed-workload replay, keep/discard+rollback,
  warmup/multi-trial/significance from the start. **Mid-point checkpoint: curve or no
  curve.** No curve → ship the scripted fallback (one slow query → `hypopg`-suggested
  index → measured win) and stop pushing the full vision.
- **Phase 2 (Day 2, ~8h)**: widen to tasks 2–5. Reroute agent comms through Kafka
  pub/sub. Postgres = memory + escalation log. Self-provisioning via MCP. Add the
  frozen escalation gate.
- **Phase 3 (final hours)**: build the stationarity gradient, run the frozen
  loop+gate across it, plot the live escalation-vs-drift curve. Demo arc: (1)
  descending p99 + cost-flat + correctness-preserved → the loop works; (2) the boundary
  curve → the autonomy is legitimate, it knows its edge; (3) Stage 2 stated as the
  research bet, data-gated, not a result.

**Open scheduling gap**: Tangled/ATProto signing of escalation records (the parallel
"two challenges, one plant" track) has **zero allocated hours** in Phases 0–3 above.
Needs an explicit decision — contingent stretch only if Phase 3 lands early, or a real
slot — rather than discovering the conflict at hour 40.

## The open question (leave it open on stage)

Is the drift rate of the interior's reward bounded or unbounded?

- Bounded → the architecture is a stable, permanent fixed point.
- Unbounded → it's a transient; the boundary advances faster than stationary mass can
  be retired into the safe region.

We cannot know which in 48h. The Phase-3 curve is the first reading of that exponent.
Presented as an instrument pointed at an open question, not an answer — that openness
is the differentiator.

## Questions to get answered on site

**Aiven engineers**
- Sandbox/throwaway service, or must we tune shared/prod? (isolation for clean
  measurement)
- Rate limits/quotas on write tools (`service_update`, `pg_write`) — loop iteration
  speed?
- Do GUC changes require a restart, or apply live? Which params are dynamic?
- Are `hypopg` + `pg_stat_statements` available on our plan?
- Metric resolution/latency from `aiven_service_metrics_fetch` — granular enough for a
  ~5-min experiment?
- Can we pull `pg_stat_statements` history to build the replay benchmark?
- Does `aiven_service_connection_info` give a direct connection for our own benchmark
  harness?
- How is projected cost surfaced so we can enforce the budget constraint live?

**Challenge owners / judges**
- Judging weighting: novelty vs. working demo vs. business value?
- Aiven-specific prize track vs. cross-cutting? Do AWS / Tangled also score?
- Preferred dataset/workload, or bring our own? Demo slot length? Constraints on
  touching live infra during the demo?

## Fallback / parallel directions

- **Tangled ATProto explainability** — now scoped as a parallel, separately-scheduled
  track (see roadmap gap above), not a fallback for this project. Custom lexicons
  (`com.sunstead.crossing`/`com.sunstead.judgment`) as signed PDS records over the
  same escalation log. Confirmed feasible; caveats: writes need user OAuth, git
  contents/collaborator data are knot-XRPC not firehose, network-wide discovery needs
  a Jetstream consumer.
- The original "membrane governance" fallback is no longer a fallback — it's been
  absorbed into the front-runner as Stage 1 (the frozen pore) and Stage 2 (the
  deferred unicorn). Nothing separate to maintain here anymore.
