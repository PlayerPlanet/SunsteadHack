#!/usr/bin/env python
"""Story A — Phase 1 runner: the first descending p99 curve on real Postgres.

This is integration point #1 (issue #2): swap the Phase-0 fixtures for Story B's
REAL harness (`cleanroom.benchmark`, `cleanroom.pore`, `cleanroom.logclient.PgLogClient`)
and run the interior loop against a live Aiven Postgres, producing a descending
p99 series written to the `experiment` table — with the noise gate rejecting
within-variance changes and a rollback on any regression.

LEGITIMACY (why the curve is trustworthy):
  The proposer ONLY proposes. It never applies, measures, or scores. Story B's
  frozen benchmark is the objective judge; `is_within_noise` is the Gate-2 guard.
  The optimizer cannot move the goalposts — so a descending curve is real signal.

SAFETY (shared service):
  Everything runs inside a dedicated, throwaway schema (default `story_a_demo`)
  seeded with our own small table. Index create/drop is fully reversible, and the
  schema is dropped on exit unless --keep-schema is passed. No teammate objects are
  touched. The DB connection is read from CLEANROOM_PG_DSN (or --dsn); credentials
  are never hardcoded. Pull a live DSN with the `aiven_service_connection_info`
  MCP tool and `export CLEANROOM_PG_DSN=...` (include sslmode=require).

Usage:
    export CLEANROOM_PG_DSN='postgres://avnadmin:...@host:port/defaultdb?sslmode=require'
    python scripts/run_phase1_curve.py                  # scripted proposer (reproducible)
    python scripts/run_phase1_curve.py --proposer claude # real ClaudeProposer (needs ANTHROPIC_API_KEY)
    python scripts/run_phase1_curve.py --keep-schema     # leave story_a_demo for inspection
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Allow `python scripts/run_phase1_curve.py` from the repo root without an editable
# install: put the repo root (this file's parent's parent) on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cleanroom.db as db_mod
from cleanroom import benchmark as benchmark_mod
from cleanroom import pore as pore_mod
from cleanroom.benchmark import register_workload
from cleanroom.db import connect
from cleanroom.logclient import PgLogClient
from cleanroom.loop import run_loop
from cleanroom.types import Candidate

# The frozen log schema (experiment/crossing/judgment). We apply it directly into
# our throwaway schema rather than via db.init_schema(), whose existence-check is
# hardcoded to `public` — on the shared service those tables already exist in
# public, so init_schema would skip and leave our isolated schema empty.
_SCHEMA_SQL_PATH = Path(db_mod.__file__).with_name("schema.sql")

_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _validate_ident(name: str, what: str) -> str:
    if not _IDENT_RE.match(name):
        raise SystemExit(f"{what} must match ^[A-Za-z0-9_]+$ (got {name!r})")
    return name


class ScriptedProposer:
    """Deterministic proposer that exercises every gate, in order.

    The interior loop is proposer-agnostic by design; for the *first* proof run we
    use a scripted sequence so the curve is reproducible and demonstrates each
    behaviour deterministically:

      1. A genuinely useful composite index on the filtered/ordered columns
         -> big p99 drop, clears the effect-size floor and the t-test -> KEEP.
      2. A useless index on a column the query never touches
         -> planner ignores it, latency unchanged -> within-noise -> DISCARD (rollback).

    Pass --proposer claude to use the real (agentic) ClaudeProposer instead; the
    legitimacy guarantee is identical because the judge, not the proposer, scores.
    """

    def __init__(self, table: str):
        self._queue = [
            Candidate(type="index", params={"table": table, "columns": ["user_id", "created_at"]}, reversible=True),
            Candidate(type="index", params={"table": table, "columns": ["amount"]}, reversible=True),
        ]
        self._table = table
        self._n = 0

    def propose(self, task_spec: dict, history: list) -> Candidate:
        if self._queue:
            return self._queue.pop(0)
        # Extra iterations: keep proposing benign no-op indexes (each will be discarded).
        self._n += 1
        return Candidate(
            type="index",
            params={"table": self._table, "columns": ["amount", "user_id"]},
            reversible=True,
        )


def _build_claude_proposer():
    # ClaudeProposer reads objective/context from the task_spec passed by run_loop,
    # which main() populates below — nothing else to wire here.
    from cleanroom.loop.proposers import ClaudeProposer

    return ClaudeProposer()


def setup_workload(conn, schema: str, table: str, rows: int, workload_id: str) -> str:
    """Create the throwaway schema + seeded table and freeze the workload SQL.

    Returns the workload SQL that was registered.
    """
    with conn.cursor() as cur:
        # Clean slate: drop any leftovers from a prior aborted run, then recreate.
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        cur.execute(f'CREATE SCHEMA "{schema}"')
        # Scope every unqualified name (workload table + log tables) to our schema.
        cur.execute(f'SET search_path TO "{schema}"')
        # Apply the frozen experiment/crossing/judgment schema into THIS schema.
        cur.execute(_SCHEMA_SQL_PATH.read_text(encoding="utf-8"))
        cur.execute(
            f'CREATE TABLE "{table}" ('
            "  id bigserial primary key,"
            "  user_id integer not null,"
            "  created_at timestamptz not null,"
            "  amount numeric not null"
            ")"
        )
        # Seed deterministically and fast, entirely server-side.
        cur.execute(
            f'INSERT INTO "{table}" (user_id, created_at, amount) '
            "SELECT (g %% 1000), "
            "       now() - ((g %% 86400) || ' seconds')::interval, "
            "       (g %% 997)::numeric "
            "FROM generate_series(1, %s) AS g",
            (rows,),
        )
        cur.execute(f'ANALYZE "{table}"')

    # A workload that is seq-scan-bound without an index but a cheap index scan with
    # one on (user_id, created_at): selective equality + ordered top-N.
    workload_sql = (
        f'SELECT id, amount FROM "{table}" '
        "WHERE user_id = 42 ORDER BY created_at DESC LIMIT 20"
    )
    register_workload(workload_id, workload_sql)
    return workload_sql


def teardown(conn, schema: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def print_curve(logclient, task_id: str, baseline_p99: float | None) -> None:
    rows = logclient.read_experiments(filter={"task_id": task_id})
    rows.sort(key=lambda r: r["id"])
    print("\n=== Phase-1 p99 curve (task_id=%s) ===" % task_id)
    if baseline_p99 is not None:
        print(f"  baseline (no candidate):  p99 = {baseline_p99:8.3f} ms")
    for r in rows:
        cand = r.get("candidate") or {}
        ctype = cand.get("type", "?")
        cols = ",".join((cand.get("params") or {}).get("columns", []))
        cp99 = r.get("candidate_p99")
        cp99_s = f"{cp99:8.3f} ms" if cp99 is not None else "   (escalated)"
        print(
            f"  exp#{r['id']:<4} {ctype:<5} on ({cols:<22}) "
            f"p99 = {cp99_s}  within_noise={r.get('within_noise')!s:<5} "
            f"-> {r['decision'].upper()}"
        )
    kept = [r for r in rows if r["decision"] == "keep"]
    print(f"\n  {len(rows)} experiment(s) logged, {len(kept)} kept.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Story A Phase-1: first descending p99 curve on real Postgres.")
    ap.add_argument("--dsn", default=None, help="Postgres DSN (else CLEANROOM_PG_DSN env).")
    ap.add_argument("--schema", default="story_a_demo", help="Throwaway schema name.")
    ap.add_argument("--table", default="events", help="Workload table name.")
    ap.add_argument("--rows", type=int, default=200_000, help="Rows to seed.")
    ap.add_argument("--iterations", type=int, default=3, help="Loop iterations (1 baseline + N-1 proposals).")
    ap.add_argument("--task-id", default="phase1-index-demo", help="task_id for the experiment log.")
    ap.add_argument("--proposer", choices=["scripted", "claude"], default="scripted")
    ap.add_argument("--model", default="deterministic-scripted", help="model label for the log.")
    ap.add_argument("--keep-schema", action="store_true", help="Do not drop the schema on exit.")
    args = ap.parse_args(argv)

    schema = _validate_ident(args.schema, "--schema")
    table = _validate_ident(args.table, "--table")

    dsn = args.dsn or os.environ.get("CLEANROOM_PG_DSN")
    if not dsn:
        print(
            "ERROR: no DSN. Set CLEANROOM_PG_DSN (or pass --dsn). Pull a live DSN with the "
            "aiven_service_connection_info MCP tool; include sslmode=require.",
            file=sys.stderr,
        )
        return 2
    if "sslmode" not in dsn:
        print("WARNING: DSN has no sslmode; Aiven requires TLS (sslmode=require).", file=sys.stderr)

    workload_id = f"{args.task_id}-wl"
    conn = connect(dsn, autocommit=True)
    try:
        workload_sql = setup_workload(conn, schema, table, args.rows, workload_id)

        if args.proposer == "claude":
            proposer = _build_claude_proposer()
            model = proposer.model
        else:
            proposer = ScriptedProposer(table)
            model = args.model

        logclient = PgLogClient(conn)

        # Measure the no-candidate baseline ourselves so the curve has a visible
        # starting point (the loop establishes the same baseline internally on iter 0).
        baseline_p99 = benchmark_mod.run_benchmark(conn, workload_id, warmup=5, trials=10).p99_ms
        print(f"Baseline p99 (seq scan, no index): {baseline_p99:.3f} ms")
        print(f"Proposer: {args.proposer}  |  iterations: {args.iterations}  |  rows: {args.rows}")

        task_spec = {
            "task_id": args.task_id,
            "model": model,
            "workload_id": workload_id,
            "conn": conn,
            "objective": f"minimize p99 of: {workload_sql}",
            "context": {
                "schema": f'{table}(id, user_id int, created_at timestamptz, amount numeric)',
                "slow_queries": workload_sql,
            },
        }

        run_loop(
            task_spec,
            proposer=proposer,
            benchmark=benchmark_mod,
            pore=pore_mod,
            logclient=logclient,
            iterations=args.iterations,
        )

        print_curve(logclient, args.task_id, baseline_p99)
        return 0
    finally:
        if args.keep_schema:
            print(f"\n(--keep-schema) schema {schema!r} left in place for inspection.")
        else:
            teardown(conn, schema)
            print(f"\nCleaned up schema {schema!r} (DROP SCHEMA CASCADE).")
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
