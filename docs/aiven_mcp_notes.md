# Aiven MCP — Setup Notes & Gotchas

> Operational reference for whoever (human or agent) touches Aiven MCP next on this
> project. Read `solution-directions.md` first for the why/architecture; this file is
> the how, plus every gotcha we hit doing Phase 0 live against the real service so
> nobody has to rediscover them.

## Current live state

- **Project:** `konsta-sunsteadhack` (org admin role confirmed). Was a completely
  clean slate when Phase 0 started — zero pre-existing services.
- **Service:** `sunstead-pg-bench` — PostgreSQL 17.10, plan `startup-8` (2 CPU/8GB,
  $0.205/hr), cloud `google-europe-north1`. State: `RUNNING`.
- **Extensions enabled** (in `defaultdb`): `pg_stat_statements` (v1.11), `vector` /
  pgvector (v0.8.1). `vectorscale` (v0.9.0) is also available if needed later.
- **PgBouncer is bundled on this plan automatically** — port 11245, pinned + unpinned
  pools both supported. No separate provisioning needed for the pool-sizing action.
- **Table created:** `escalation_log` (Stage 0 artifact) — see schema below.
- **Kafka: not provisioned yet**, deliberately. Phase 1 is Postgres-only per the
  roadmap; Kafka comes in Phase 2 (agent comms + secondary tuning target).

`escalation_log` schema (already live, treat this as source of truth, not the doc):
```sql
CREATE TABLE escalation_log (
    id BIGSERIAL PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    task_type TEXT NOT NULL,
    proposed_action JSONB NOT NULL,
    context JSONB NOT NULL,
    retrieval_trace JSONB,
    embedding vector(1536),
    gate_triggered TEXT,
    escalated BOOLEAN NOT NULL DEFAULT false,
    judgment TEXT,
    judge_actor TEXT NOT NULL,
    rationale TEXT,
    metric_before JSONB,
    metric_after JSONB,
    drift_distance NUMERIC,
    rolled_back BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_escalation_log_task_created ON escalation_log (task_type, created_at);
```
`embedding` is `vector(1536)` (OpenAI ada-002/3-small dimension) — change this if the
final embedding model differs; pgvector requires a fixed dimension per column.

## Access — if you hit a 403

If `aiven_project_list` returns an empty `projects: []`, or `aiven_service_list`/
similar returns `403 Not a project member` on `konsta-sunsteadhack` — this is an MCP
plugin credential problem, not a typo'd project name. An empty `project_list` means
the configured token has zero project memberships anywhere. Fix the plugin's
Aiven auth config; don't try alternate project name spellings.

## Gotchas discovered doing Phase 0 — read before writing experiment-loop code

1. **`hypopg` is NOT available** on this service/plan. The original action-space plan
   (hypothetical index testing via `hypopg`+`EXPLAIN`, no real build) doesn't work
   here. Adjusted design: actually `CREATE INDEX`, measure, then `COMMIT` (keep) or
   `ROLLBACK` (discard) inside one real transaction. Still cheap/reversible on a
   benchmark-sized dataset — just not free-as-hypothetical.

2. **`aiven_pg_write`/`aiven_pg_read` are one-statement, one-shot tools.** Each call
   appears to run in its own implicit transaction (confirmed: `ALTER SYSTEM` was
   rejected with Postgres error 25001, "cannot run inside a transaction block" — that's
   a hard Postgres rule, triggered because the tool wraps the call in one). Consequences:
   - Cannot run `ALTER SYSTEM` through this tool at all.
   - Cannot hold a transaction open across multiple tool calls (no `BEGIN` in call 1,
     work in call 2, `COMMIT`/`ROLLBACK` in call 3).
   - **The real experiment-loop Worker needs its own persistent, directly-held DB
     connection** (e.g. `psycopg`), with manual transaction/autocommit control — not
     these chat-session MCP tools. Use the MCP tools for one-off admin/investigation
     only (creating tables, checking extensions, etc.), not for the actual tuning loop.

3. **`aiven_pg_write` blocks:** `DROP`, `TRUNCATE`, `GRANT`, `REVOKE`, `REASSIGN`,
   `SECURITY LABEL`, `DO`, `CREATE FUNCTION`, `CREATE PROCEDURE`. One SQL statement per
   call — semicolon-separated multi-statements are rejected outright.

4. **GUC dynamic vs. restart-required** (confirmed via
   `SELECT name, setting, context FROM pg_settings WHERE name IN (...)`):
   - Live, no restart (`context=user`): `work_mem`, `random_page_cost`.
   - Restart-required (`context=postmaster`): `shared_buffers`, `max_connections`,
     `pg_stat_statements.max`.
   - Exclude `shared_buffers` from the fast interior-loop action space — it costs a
     restart per trial, too slow to iterate on.

5. **`aiven_service_metrics_fetch` gives infra telemetry, not query latency.**
   CPU/disk/memory/network/load only, at 30-second resolution (`period="hour"` ≈ 120
   points/host/metric — matches observed real data exactly). Useful for cost/guardrail
   monitoring during an experiment window. **Not** the source for the p99 judge metric
   — that has to be measured directly by our own benchmark harness timing its own query
   execution.

6. **Extensions must be `CREATE EXTENSION`'d per-database even if the library is
   already preloaded server-side.** `pg_stat_statements.max` showed up in `pg_settings`
   (proving the library was preloaded) but `SELECT * FROM pg_stat_statements` still
   failed with "relation does not exist" until we explicitly ran
   `CREATE EXTENSION pg_stat_statements`.

7. **`aiven_service_connection_info` returns real live credentials into the chat
   transcript.** Only call it once application code actually needs to connect, and
   write the result straight into a gitignored `.env`/secret store rather than leaving
   it sitting in conversation history.

8. **Provisioning costs real money, even if small.** `aiven_service_create` needs an
   explicit plan choice — always check `aiven_service_type_plans` +
   `aiven_service_plan_pricing` first and let a human pick; don't default silently.
   (For reference: `hobbyist` $0.026/hr, `startup-4` $0.103/hr, `startup-8` $0.205/hr
   in `google-europe-north1`, as of 2026-06-24.)

## Recommended sequence for picking this up cold

1. Read `solution-directions.md` for why this exists and what it's measuring.
2. Read this file for how, and to skip re-discovering the above.
3. Call `aiven_service_get(project="konsta-sunsteadhack", service_name="sunstead-pg-bench")`
   to confirm current live state before assuming anything here is still accurate —
   this file is a snapshot, the service is the source of truth.
