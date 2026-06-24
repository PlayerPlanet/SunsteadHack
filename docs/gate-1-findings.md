# Gate-1 Findings — Aiven Infra Verification

> Verified **2026-06-24** against the live service via the Aiven MCP surface (read-only
> probes only). These answer the make-or-fail gates in
> [`solution-directions.md`](solution-directions.md) that can be checked without being on
> site. Where a fact changes a story's plan, it has been propagated to the relevant GitHub
> issue.

**Project:** `konsta-sunsteadhack` (cloud `google-europe-north1`)
**Service:** `sunstead-pg-bench` — type `pg`, **RUNNING**, **PostgreSQL 17.10**
(teammate-provisioned; DB currently empty — no user tables yet).

---

## Gate 1 + 2 — Freezable workload / signal-beats-noise: ✅ PASS

Measured with repeated read-only `EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON)` over a
deterministic CPU-bound query (`md5()` over `generate_series` + sort + count) — no data load
required.

- **Workload is fully deterministic** — identical plan, cost, and row counts on every run.
  The *workload itself* is freezable; the only question is timing stability.
- **Clean noise floor ≈ CV 6.5 %** — sequential, in-memory runs: **215.7 ± 14 ms** (n=4;
  three of four within ~2 %).
- **Two noise sources, both controllable:**
  - **Concurrency** inflated CV to ~22 % (5 parallel runs fighting for CPU). → Run trials
    **sequentially**.
  - **Disk spill** — a 1M-row sort spilled to disk (`external merge`, `Sort Space Type:
    Disk`, ~39 MB) because `work_mem` is only **7 MB**. → Size the working set to stay in
    memory, or `SET work_mem` per session (it is a **dynamic** GUC — see below).

**Verdict:** a real index/GUC win of 20–50 % clears the ~6 % noise floor comfortably,
especially with warmup + median/p99-of-N trials + a significance test (the `is_within_noise`
gate in issue #3).

## Extensions

| Extension | Status | Use |
|---|---|---|
| `pg_stat_statements` (1.11) | ✅ available | per-query stats; secondary replay workload |
| `pg_stat_monitor` (2.1) | ✅ available | **native p99 percentile buckets** — read p99 directly instead of computing from samples |
| `pg_prewarm` / `pg_buffercache` | ✅ available | warmup control for the benchmark |
| `pg_repack` | ✅ available | online table reorg — a reversible action candidate |
| `pg_cron` | ✅ available | loop scheduling |
| **`hypopg`** | ❌ **NOT available** | (0 of 60 installable extensions; no `pg_hint_plan` either) |

**Impact of no `hypopg`:** the "evaluate a hypothetical index without building it" path is
closed. Substitute (now in issue #2): **real `CREATE INDEX` / `DROP INDEX` on a small
dataset** — reversible, sub-second build (`maintenance_work_mem` ≈ 508 MB → in-memory build),
and *more honest* than a cost-only estimate because it measures the real index.

## Tunable GUCs — dynamic vs restart-required

Read from `pg_settings.context`. **`user` = settable live, no restart**; **`postmaster` =
requires a service restart** (rolling restart via `aiven_service_update`).

| GUC | Value | Context | Loop can apply live? |
|---|---|---|---|
| `work_mem` | 7 MB | `user` | ✅ live |
| `maintenance_work_mem` | ~508 MB | `user` | ✅ live |
| `effective_cache_size` | ~4.6 GB | `user` | ✅ live |
| `random_page_cost` | 1 (SSD) | `user` | ✅ live |
| `jit` | on | `user` | ✅ live |
| `max_parallel_workers_per_gather` | 2 | `user` | ✅ live |
| `default_statistics_target` | 100 | `user` | ✅ live |
| `shared_buffers` | ~1.59 GB | `postmaster` | ⚠️ restart |
| `max_connections` | 200 | `postmaster` | ⚠️ restart |

→ Story A's GUC-tuning task can apply **most** candidates live; flag `shared_buffers` /
`max_connections` as slow restart-required experiments.

## Service sizing (for the harness)

~4 GB-class plan: `shared_buffers` ≈ 1.59 GB, `effective_cache_size` ≈ 4.6 GB,
`max_connections` = 200, SSD-tuned (`random_page_cost` = 1).

## Connection

`aiven_service_connection_info` is available (the connector has `allow_secrets=true`), so a
real `psycopg` connection can be wired for the benchmark harness when building. *Not pulled
yet* — it returns live credentials into the transcript, so fetch it only at wire-up time.

---

## Still open (need an on-site answer or a write action)

- **MCP write-tool rate limits** (`service_update`, `pg_write`) — sets how fast the loop can
  iterate. Not remotely inferable.
- **Live cost read** for the budget constraint (`aiven_service_plan_pricing` /
  metrics) — confirm granularity for enforcing "cost ≤ budget".
- **Real workload choice** — DB is empty. Decide pgbench (fast to stand up, good for the
  first descending curve) vs Join Order Benchmark (slower load, better story for breaking the
  optimizer). Recommendation: pgbench for the first curve, JOB if time allows.
