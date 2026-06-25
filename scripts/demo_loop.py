#!/usr/bin/env python3
"""End-to-end demo runner for the cleanroom autoresearch loop.

Runs the WHOLE loop — propose -> pore gate -> apply -> benchmark -> decide -> log —
wired with the real Story B substrate (real pore, real is_within_noise, real
check_correctness, real PgLogClient).

Two modes, auto-detected:

  * REAL DB MODE  (env CLEANROOM_PG_DSN is set):
        Seeds a demo table on the live Postgres, registers a real slow workload,
        and drives the loop with REAL query timing + REAL `CREATE INDEX` actions +
        REAL Postgres logging. This is the true e2e path.

  * OFFLINE MODE  (no DSN):
        Same loop and the same real pore / statistics, but query timing comes from
        the canned fixture (no DB needed). Lets you see the control flow — keep /
        discard / escalate — with zero setup.

Run from the repo root:

    uv run python scripts/demo_loop.py

For the real path, first export a live DSN (pull it via the aiven_service_connection_info
MCP tool — do NOT hardcode it):

    export CLEANROOM_PG_DSN="postgresql://avnadmin:...@sunstead-pg-bench-...aivencloud.com:11244/defaultdb?sslmode=require"
    uv run python scripts/demo_loop.py
"""

import os
import sys
from pathlib import Path


def _load_dotenv():
    """Load KEY=VALUE lines from a repo-root .env into os.environ (no dependency).

    Existing environment variables win, so an explicit `export` still overrides
    the file. Lines that are blank or start with '#' are ignored.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


_load_dotenv()

from cleanroom import benchmark
from cleanroom import pore
from cleanroom.loop import run_loop
from cleanroom.types import Candidate


# --------------------------------------------------------------------------- #
# A tiny scripted proposer that exercises keep / discard / escalate.          #
# (The real ClaudeProposer lives in cleanroom/loop/proposers.py; this keeps   #
#  the demo deterministic and API-key-free.)                                  #
# --------------------------------------------------------------------------- #
class ScriptedProposer:
    def __init__(self, candidates):
        self._candidates = list(candidates)
        self._i = 0

    def propose(self, task_spec, history):
        if self._i < len(self._candidates):
            c = self._candidates[self._i]
            self._i += 1
            return c
        # Past the script: a benign no-op the loop will discard.
        return Candidate(type="index", params={"table": "noop", "columns": ["x"]}, reversible=True)


DEMO_TABLE = "demo_events"
WORKLOAD_ID = "demo_events_lookup"

# The three candidates that tell the whole story:
#   1) a genuinely useful composite index   -> KEEP   (real measured win)
#   2) a useless index on an unrelated col  -> DISCARD (within noise)
#   3) a high-blast-radius GUC change        -> ESCALATE (pore stops it, asks a human)
DEMO_CANDIDATES = [
    Candidate(type="index", params={"table": DEMO_TABLE, "columns": ["user_id", "created_at"]}, reversible=True),
    Candidate(type="index", params={"table": DEMO_TABLE, "columns": ["payload"]}, reversible=True),
    Candidate(type="guc", params={"name": "shared_buffers", "value": "2GB"}, reversible=True),
]


def print_log(logclient, cold_baseline_p99=None):
    print("\n=== experiment log ===")
    kept_p99 = None
    for e in logclient.read_experiments():
        p99 = "n/a" if e["candidate_p99"] is None else f"{e['candidate_p99']:.1f}ms"
        base = "n/a" if e["baseline_p99"] is None else f"{e['baseline_p99']:.1f}ms"
        print(f"  exp {e['id']}: decision={e['decision']:<10} baseline={base:<9} candidate={p99}")
        if e["decision"] == "keep" and e["candidate_p99"] is not None:
            kept_p99 = e["candidate_p99"]
    # crossings (escalations) live in their own table for PgLogClient; the in-memory
    # fixture exposes them as an attribute.
    crossings = getattr(logclient, "crossings", None)
    if crossings:
        print("  --- escalations (pore stopped these, routed to a human) ---")
        for c in crossings:
            print(f"    crossing {c['id']}: pore={c['pore']} risk={c['risk_level']}")
    # The headline: cold seq-scan baseline -> autonomously-kept index.
    if cold_baseline_p99 is not None and kept_p99 is not None:
        delta = 100.0 * (cold_baseline_p99 - kept_p99) / cold_baseline_p99
        print(
            f"\n  >>> autonomous win: p99 {cold_baseline_p99:.1f}ms -> {kept_p99:.1f}ms "
            f"({delta:+.0f}%), kept with zero human approval; "
            f"the high-blast-radius change was escalated instead."
        )


def run_offline():
    """Real pore + real stats + canned timing. No DB required."""
    from cleanroom.fixtures import CannedBenchmark, InMemoryLogClient

    class HybridBench:
        """Canned timing, but the REAL Story B correctness + noise statistics."""
        def __init__(self):
            self._canned = CannedBenchmark(baseline_p99=100.0)

        def run_benchmark(self, conn, workload_id, *, warmup=5, trials=10):
            return self._canned.run_benchmark(conn, workload_id, warmup=warmup, trials=trials)

        def check_correctness(self, conn, candidate):
            return benchmark.check_correctness(conn, candidate)

        def is_within_noise(self, baseline_samples, candidate_samples):
            return benchmark.is_within_noise(baseline_samples, candidate_samples)

    print(">>> OFFLINE MODE (no CLEANROOM_PG_DSN) — real pore/stats, canned timing\n")
    log = InMemoryLogClient()
    run_loop(
        {"task_id": "demo-offline", "model": "scripted", "workload_id": ""},
        proposer=ScriptedProposer(DEMO_CANDIDATES),
        benchmark=HybridBench(),
        pore=pore,
        logclient=log,
        iterations=len(DEMO_CANDIDATES) + 1,
    )
    print_log(log)
    print("\n(Offline note: canned timing means every applied candidate 'improves' — "
          "the discard/escalate decisions are the real signal here. Run with a DSN for true timing.)")


def run_real(dsn):
    """True e2e: live Postgres, real timing, real CREATE INDEX, real logging."""
    import psycopg

    from cleanroom.actions import _make_index_name
    from cleanroom.db import init_schema
    from cleanroom.logclient import PgLogClient

    print(">>> REAL DB MODE — live Postgres timing + CREATE INDEX + Postgres logging\n")
    conn = psycopg.connect(dsn)

    # 1) Make sure the log tables exist, then clear prior demo rows so each run
    #    shows a clean log (only touches rows from this demo's task_ids).
    init_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM judgment WHERE crossing_id IN ("
            "  SELECT c.id FROM crossing c JOIN experiment e ON c.experiment_id = e.id "
            "  WHERE e.task_id LIKE 'demo-%')"
        )
        cur.execute(
            "DELETE FROM crossing WHERE experiment_id IN ("
            "  SELECT id FROM experiment WHERE task_id LIKE 'demo-%')"
        )
        cur.execute("DELETE FROM experiment WHERE task_id LIKE 'demo-%'")
        conn.commit()

    # 2) Seed a demo table (idempotent: only seed if empty).
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS {DEMO_TABLE} ("
            "  id bigserial primary key,"
            "  user_id integer not null,"
            "  created_at timestamptz not null,"
            "  payload text not null)"
        )
        conn.commit()
        cur.execute(f"SELECT count(*) FROM {DEMO_TABLE}")
        n = cur.fetchone()[0]
        if n == 0:
            print(f"    seeding {DEMO_TABLE} with 200k rows ...")
            cur.execute(
                f"INSERT INTO {DEMO_TABLE} (user_id, created_at, payload) "
                "SELECT mod(g, 1000), now() - (random() * interval '30 days'), md5(g::text) "
                "FROM generate_series(1, 200000) g"
            )
            conn.commit()
        else:
            print(f"    {DEMO_TABLE} already has {n} rows, skipping seed")

        # 3) Reset to a clean baseline: drop the index the demo will (re)discover,
        #    so every run starts from a seq-scan baseline.
        idx = _make_index_name(DEMO_TABLE, ["user_id", "created_at"])
        cur.execute(f'DROP INDEX IF EXISTS "{idx}"')
        conn.commit()

    # 4) Freeze the workload: a selective lookup that a (user_id, created_at) index
    #    turns from a seq scan into an index scan.
    benchmark.register_workload(
        WORKLOAD_ID,
        f"SELECT count(*) FROM {DEMO_TABLE} "
        "WHERE user_id = 42 AND created_at >= now() - interval '7 days'",
    )

    # 5) Measure the cold (no-index) baseline ONCE for display. The loop establishes
    #    its own internal baseline too, but logs the post-keep value — so we capture
    #    the real "before" here to make the descending win visible.
    cold = benchmark.run_benchmark(conn, WORKLOAD_ID, warmup=5, trials=10)
    print(f"\n    cold baseline (seq scan, no index): p99 = {cold.p99_ms:.1f}ms\n")

    log = PgLogClient(conn)
    run_loop(
        {"task_id": "demo-real", "model": "scripted", "workload_id": WORKLOAD_ID, "conn": conn},
        proposer=ScriptedProposer(DEMO_CANDIDATES),
        benchmark=benchmark,      # the module itself exposes the 3 contract functions
        pore=pore,
        logclient=log,
        iterations=len(DEMO_CANDIDATES) + 1,
    )
    print_log(log, cold_baseline_p99=cold.p99_ms)
    conn.close()


def main():
    dsn = os.environ.get("CLEANROOM_PG_DSN")
    if dsn:
        run_real(dsn)
    else:
        run_offline()
    return 0


if __name__ == "__main__":
    sys.exit(main())
