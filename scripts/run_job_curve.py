#!/usr/bin/env python
"""JOB-complex query optimization — a descending p99 curve on a real multi-join.

A trimmed Join Order Benchmark (IMDB-shaped) workload: a five-table join
(title ⋈ cast_info ⋈ movie_keyword ⋈ keyword ⋈ kind_type) with selective filters.
Unindexed it is sequential scans + hash joins; the loop discovers the remedies that
matter for a complex join — join-key indexes AND extended statistics on the
correlated filter columns (the new `statistics` action; the canonical JOB fix for
cardinality misestimation).

Same isolation discipline as run_phase1_curve.py: a throwaway schema (workload +
log tables), reversible CREATE/DROP INDEX & CREATE/DROP STATISTICS, DROP SCHEMA
CASCADE on exit. Connection from CLEANROOM_PG_DSN (or --dsn); never hardcoded.

    export CLEANROOM_PG_DSN='postgres://…?sslmode=require'
    python scripts/run_job_curve.py
    python scripts/run_job_curve.py --scale 20 --keep-schema
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cleanroom.db as db_mod
from cleanroom import benchmark as benchmark_mod
from cleanroom import pore as pore_mod
from cleanroom.benchmark import register_workload
from cleanroom.db import connect
from cleanroom.logclient import PgLogClient
from cleanroom.loop import run_loop
from cleanroom.types import Candidate

_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")
_SCHEMA_SQL_PATH = Path(db_mod.__file__).with_name("schema.sql")

# A trimmed JOB / IMDB-shaped schema (no secondary indexes — the loop builds those).
_JOB_TABLES_DDL = """
CREATE TABLE kind_type (id int primary key, kind text not null);
CREATE TABLE title (id int primary key, title text not null,
                    production_year int, kind_id int references kind_type(id));
CREATE TABLE name (id int primary key, name text not null);
CREATE TABLE keyword (id int primary key, keyword text not null);
CREATE TABLE cast_info (id int primary key, person_id int references name(id),
                        movie_id int references title(id), role_id int, nr_order int);
CREATE TABLE movie_keyword (id int primary key, movie_id int references title(id),
                            keyword_id int references keyword(id));
"""

# The JOB-complex workload: a 5-table join with correlated filters. Deterministic.
_JOB_QUERY = (
    "SELECT t.id, t.title, count(*) AS n "
    "FROM title t "
    "JOIN cast_info ci ON ci.movie_id = t.id "
    "JOIN movie_keyword mk ON mk.movie_id = t.id "
    "JOIN keyword k ON k.id = mk.keyword_id "
    "JOIN kind_type kt ON kt.id = t.kind_id "
    "WHERE t.production_year BETWEEN 2000 AND 2010 AND kt.kind = 'movie' "
    "GROUP BY t.id, t.title ORDER BY n DESC, t.id LIMIT 20"
)


def _validate_ident(name: str, what: str) -> str:
    if not _IDENT_RE.match(name):
        raise SystemExit(f"{what} must match ^[A-Za-z0-9_]+$ (got {name!r})")
    return name


class JobProposer:
    """Deterministic remedy sequence for the JOB-complex join (reproducible curve).

    Exercises the remedies that matter for a complex join, in order of leverage:
      1. index cast_info(movie_id)        — the heaviest join key (big drop)
      2. index movie_keyword(movie_id)    — second join key
      3. statistics title(production_year, kind_id) — extended stats for the
         correlated filter (the NEW action; the canonical JOB cardinality fix)
      4. index movie_keyword(keyword_id)  — keyword join key

    The loop keeps each only if it genuinely beats the running baseline outside noise.
    """

    def __init__(self):
        self._queue = [
            Candidate(type="index", params={"table": "cast_info", "columns": ["movie_id"]}, reversible=True),
            Candidate(type="index", params={"table": "movie_keyword", "columns": ["movie_id"]}, reversible=True),
            Candidate(type="statistics",
                      params={"table": "title", "columns": ["production_year", "kind_id"],
                              "kinds": ["ndistinct", "dependencies"]},
                      reversible=True),
            Candidate(type="index", params={"table": "movie_keyword", "columns": ["keyword_id"]}, reversible=True),
        ]

    def propose(self, task_spec: dict, history: list) -> Candidate:
        if self._queue:
            return self._queue.pop(0)
        # Extra iterations: a benign no-op index (will be discarded).
        return Candidate(type="index", params={"table": "name", "columns": ["name"]}, reversible=True)


def setup_job(conn, schema: str, scale: int, workload_id: str) -> str:
    """Create the throwaway schema, the JOB tables + scaled data, and freeze the query."""
    n_title = 6000 * scale
    n_name = 4000 * scale
    n_keyword = 600 * scale
    n_cast = 30000 * scale
    n_mk = 10000 * scale
    with conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        cur.execute(f'CREATE SCHEMA "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
        cur.execute(_SCHEMA_SQL_PATH.read_text(encoding="utf-8"))  # experiment/crossing/judgment/run
        cur.execute(_JOB_TABLES_DDL)
        cur.execute("INSERT INTO kind_type (id, kind) VALUES (1,'movie'),(2,'tv series'),(3,'video'),(4,'episode')")
        cur.execute("INSERT INTO title (id, title, production_year, kind_id) "
                    "SELECT g, 'title_'||g, 1950 + (g %% 71), 1 + (g %% 4) FROM generate_series(1,%s) g", (n_title,))
        cur.execute("INSERT INTO name (id, name) SELECT g, 'person_'||g FROM generate_series(1,%s) g", (n_name,))
        cur.execute("INSERT INTO keyword (id, keyword) SELECT g, 'kw_'||g FROM generate_series(1,%s) g", (n_keyword,))
        cur.execute("INSERT INTO cast_info (id, person_id, movie_id, role_id, nr_order) "
                    "SELECT g, 1+(g %% %s), 1+(g %% %s), 1+(g %% 12), 1+(g %% 30) FROM generate_series(1,%s) g",
                    (n_name, n_title, n_cast))
        cur.execute("INSERT INTO movie_keyword (id, movie_id, keyword_id) "
                    "SELECT g, 1+(g %% %s), 1+(g %% %s) FROM generate_series(1,%s) g",
                    (n_title, n_keyword, n_mk))
        cur.execute("ANALYZE")
    register_workload(workload_id, _JOB_QUERY)
    return _JOB_QUERY


def teardown(conn, schema: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def print_curve(logclient, task_id: str, baseline_p99: float | None) -> None:
    rows = sorted(logclient.read_experiments(filter={"task_id": task_id}), key=lambda r: r["id"])
    print(f"\n=== JOB-complex p99 curve (task_id={task_id}) ===")
    if baseline_p99 is not None:
        print(f"  baseline (no remedy):     p99 = {baseline_p99:8.2f} ms")
    for r in rows:
        cand = r.get("candidate") or {}
        ctype = cand.get("type", "?")
        params = cand.get("params") or {}
        tgt = f"{params.get('table','?')}({','.join(params.get('columns', []))})"
        cp99 = r.get("candidate_p99")
        cp99_s = f"{cp99:8.2f} ms" if cp99 is not None else "  (escalated)"
        print(f"  {ctype:<10} {tgt:<34} p99 = {cp99_s}  -> {r['decision'].upper()}")
    kept = [r for r in rows if r["decision"] == "keep"]
    print(f"\n  {len(rows)} experiments, {len(kept)} kept "
          f"({sum(1 for r in kept if (r.get('candidate') or {}).get('type')=='statistics')} via the new statistics action).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="JOB-complex query optimization curve on real Postgres.")
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--schema", default="job_demo")
    ap.add_argument("--scale", type=int, default=10, help="Row multiplier over the trimmed-JOB base counts.")
    ap.add_argument("--iterations", type=int, default=5, help="1 baseline + N-1 remedy proposals.")
    ap.add_argument("--task-id", default="job-complex-demo")
    ap.add_argument("--keep-schema", action="store_true")
    args = ap.parse_args(argv)

    schema = _validate_ident(args.schema, "--schema")
    dsn = args.dsn or os.environ.get("CLEANROOM_PG_DSN")
    if not dsn:
        print("ERROR: no DSN. Set CLEANROOM_PG_DSN (or --dsn); include sslmode=require.", file=sys.stderr)
        return 2
    if "sslmode" not in dsn:
        print("WARNING: DSN has no sslmode; Aiven requires TLS.", file=sys.stderr)

    workload_id = f"{args.task_id}-wl"
    conn = connect(dsn, autocommit=True)
    try:
        query = setup_job(conn, schema, args.scale, workload_id)
        print(f"JOB-complex workload (scale {args.scale}): {query[:70]}…")
        logclient = PgLogClient(conn)
        baseline_p99 = benchmark_mod.run_benchmark(conn, workload_id, warmup=3, trials=8).p99_ms
        print(f"Baseline p99 (no indexes/stats): {baseline_p99:.2f} ms")

        task_spec = {"task_id": args.task_id, "model": "job-scripted", "workload_id": workload_id, "conn": conn}
        run_loop(task_spec, proposer=JobProposer(), benchmark=benchmark_mod,
                 pore=pore_mod, logclient=logclient, iterations=args.iterations)
        print_curve(logclient, args.task_id, baseline_p99)
        return 0
    finally:
        if args.keep_schema:
            print(f"\n(--keep-schema) schema {schema!r} left in place.")
        else:
            teardown(conn, schema)
            print(f"\nCleaned up schema {schema!r} (DROP SCHEMA CASCADE).")
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
