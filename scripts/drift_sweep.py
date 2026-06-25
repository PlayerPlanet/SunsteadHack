#!/usr/bin/env python
"""Story F (#16) — populate the spatial boundary curve with real drift-varied data.

Runs the REAL interior loop (cleanroom.loop.run_loop) at several drift levels against
progressively-perturbed workloads, logging real experiment/crossing rows, then draws
the escalation-rate-vs-drift curve with the existing Story-C analysis
(cleanroom.boundary.escalation_rate_by_drift) + dashboard. The escalation↔drift
coupling is the FROZEN stationarity tripwire (cleanroom.pore.stationarity), a labeled
proxy for `authority ∝ stationarity` — NOT a learned threshold.

    export CLEANROOM_PG_DSN='postgres://…?sslmode=require'
    python scripts/drift_sweep.py                 # live, isolated schema on the service
    python scripts/drift_sweep.py --mock          # offline (CannedBenchmark, in-memory)

Mirrors run_phase1_curve.py / run_job_curve.py isolation: a throwaway schema, reversible
CREATE/DROP INDEX, DROP SCHEMA CASCADE on exit. Connection from CLEANROOM_PG_DSN (or
--dsn); never hardcoded.
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cleanroom.db as db_mod
from cleanroom import benchmark as benchmark_mod
from cleanroom.benchmark import register_workload
from cleanroom.boundary import escalation_rate_by_drift, escalations_per_unit_work
from cleanroom.loop import run_loop
from cleanroom.pore.stationarity import DEFAULT_THRESHOLD, StationarityProxyPore
from cleanroom.types import Candidate

_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")
_SCHEMA_SQL_PATH = Path(db_mod.__file__).with_name("schema.sql")

DRIFT_LEVELS = [0.0, 0.25, 0.5, 0.75, 1.0]  # >=5 distinct levels (DoD)

# A simple home workload: an events table indexed on created_at. The low-drift query
# lives inside the indexed region; higher drift widens the window and adds off-index
# predicates so the workload leaves what the home index covers.
_EVENTS_DDL = """
CREATE TABLE events (
    id bigint primary key,
    user_id int not null,
    created_at timestamptz not null,
    status text not null,
    amount int not null
);
CREATE INDEX events_created_at_idx ON events (created_at);
"""

_STATUSES = ("ok", "pending", "failed", "refunded")


def drifted_workload_sql(drift: float) -> str:
    """Produce the frozen SQL for a given drift level.

    drift 0.0 -> narrow, index-covered window (the trusted home query).
    Higher drift -> widen the time window AND add progressively off-index predicates
    (status, then a wide amount range), shifting the query off what the home index
    covers. The bytes are deterministic in `drift`, so each is a freezable workload.
    """
    window_days = int(round(7 + drift * 358))  # 7d (home) -> ~1y
    clauses = [f"created_at >= now() - interval '{window_days} days'"]
    if drift >= 0.5:
        clauses.append("status = 'pending'")          # unindexed column
    if drift >= 0.75:
        clauses.append("amount > 10")                 # wide, unindexed range -> seq scan
    where = " AND ".join(clauses)
    return f"SELECT count(*), avg(amount) FROM events WHERE {where}"


class DriftSweepProposer:
    """Deterministic reversible-index proposals targeting the drifted predicates.

    Below the stationarity threshold these are applied/measured by the base gate;
    above it the tripwire escalates them. All reversible, so the base gate treats
    them as auto-safe (the rise comes from the frozen drift rule, not the candidate).
    """

    def __init__(self):
        self._queue = [
            Candidate(type="index", params={"table": "events", "columns": ["status"]}, reversible=True),
            Candidate(type="index", params={"table": "events", "columns": ["status", "created_at"]}, reversible=True),
            Candidate(type="index", params={"table": "events", "columns": ["user_id"]}, reversible=True),
            Candidate(type="index", params={"table": "events", "columns": ["amount"]}, reversible=True),
        ]

    def propose(self, task_spec: dict, history: list) -> Candidate:
        if self._queue:
            return self._queue.pop(0)
        return Candidate(type="index", params={"table": "events", "columns": ["created_at", "status"]}, reversible=True)


def _validate_ident(name: str, what: str) -> str:
    if not _IDENT_RE.match(name):
        raise SystemExit(f"{what} must match ^[A-Za-z0-9_]+$ (got {name!r})")
    return name


def setup_schema(conn, schema: str, scale: int) -> None:
    n = 20000 * scale
    with conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        cur.execute(f'CREATE SCHEMA "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
        cur.execute(_SCHEMA_SQL_PATH.read_text(encoding="utf-8"))  # experiment/crossing/judgment/run
        cur.execute(_EVENTS_DDL)
        cur.execute(
            "INSERT INTO events (id, user_id, created_at, status, amount) "
            "SELECT g, 1 + (g %% 1000), "
            "       now() - (random() * interval '365 days'), "
            "       (ARRAY['ok','pending','failed','refunded'])[1 + (g %% 4)], "
            "       (g %% 500) "
            "FROM generate_series(1, %s) g",
            (n,),
        )
        cur.execute("ANALYZE")


def teardown(conn, schema: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def run_sweep(*, logclient, benchmark, conn, threshold: float, iterations: int,
              register: bool = True, verbose: bool = True) -> None:
    """Run run_loop once per drift level with a frozen StationarityProxyPore."""
    for d in DRIFT_LEVELS:
        workload_id = f"storyf-drift-{d:.2f}"
        if register:
            register_workload(workload_id, drifted_workload_sql(d))
        task_spec = {"task_id": "storyf-drift-sweep", "model": "scripted",
                     "workload_id": workload_id, "drift_level": d, "conn": conn}
        pore = StationarityProxyPore(drift_level=d, threshold=threshold)
        run_loop(task_spec, proposer=DriftSweepProposer(), benchmark=benchmark,
                 pore=pore, logclient=logclient, iterations=iterations)
        if verbose:
            print(f"  drift={d:.2f}  (window={int(round(7 + d * 358))}d, "
                  f"{'ESCALATE-all' if d > threshold else 'base-gate'})")


def draw_curve(logclient, threshold: float) -> None:
    print(f"\n=== Spatial boundary curve (escalation rate vs drift) — T={threshold} ===")
    print("    PROXY / lower bound of the legitimacy edge — a FROZEN stationarity tripwire,")
    print("    NOT the calibrated OOD membrane (the deferred Stage-2 bet).")
    for row in escalation_rate_by_drift(logclient):
        bar = "#" * int(round(row["escalation_rate"] * 36))
        print(f"  drift={row['drift_level']:.2f}  {row['escalation_rate']:5.1%}  n={row['n']:>3}  {bar}")
    print("\n=== Longitudinal (escalations per unit work) — flat within a fixed regime ===")
    for row in escalations_per_unit_work(logclient, window_size=4):
        print(f"  vol={row['cumulative_experiments']:>3}  {row['ratio']:5.1%}  ({row['escalated']}/{row['total']})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Story F drift sweep — spatial boundary curve on real data.")
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--schema", default="storyf_drift")
    ap.add_argument("--scale", type=int, default=1, help="Row multiplier over the 20k base.")
    ap.add_argument("--iterations", type=int, default=5, help="1 baseline + N-1 proposals per drift level.")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Frozen stationarity T (constant).")
    ap.add_argument("--mock", action="store_true", help="Offline: CannedBenchmark + in-memory log, no DB.")
    ap.add_argument("--keep-schema", action="store_true")
    args = ap.parse_args(argv)

    if args.mock:
        from cleanroom.fixtures import CannedBenchmark, InMemoryLogClient
        logclient = InMemoryLogClient()
        print("[mock] offline drift sweep — CannedBenchmark, in-memory log, no DB.")
        run_sweep(logclient=logclient, benchmark=CannedBenchmark(), conn=None,
                  threshold=args.threshold, iterations=args.iterations, register=False)
        draw_curve(logclient, args.threshold)
        return 0

    schema = _validate_ident(args.schema, "--schema")
    dsn = args.dsn or os.environ.get("CLEANROOM_PG_DSN")
    if not dsn:
        print("ERROR: no DSN. Set CLEANROOM_PG_DSN (or --dsn); include sslmode=require. "
              "Or run with --mock for the offline curve.", file=sys.stderr)
        return 2
    if "sslmode" not in dsn:
        print("WARNING: DSN has no sslmode; Aiven requires TLS.", file=sys.stderr)

    from cleanroom.db import connect
    from cleanroom.logclient import PgLogClient

    conn = connect(dsn, autocommit=True)
    try:
        setup_schema(conn, schema, args.scale)
        logclient = PgLogClient(conn)
        print(f"Story F drift sweep (scale {args.scale}, T={args.threshold}) on isolated schema {schema!r}.")
        run_sweep(logclient=logclient, benchmark=benchmark_mod, conn=conn,
                  threshold=args.threshold, iterations=args.iterations)
        draw_curve(logclient, args.threshold)
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
