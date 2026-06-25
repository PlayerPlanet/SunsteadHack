"""Backend factory — centralized persistent-vs-inmemory selection for Story D Phase 1.

This module is the single point where both the CLI and MCP adapters select storage
backends based on environment variables. It enables persistent state across
separate processes (e.g., Claude Code slash commands) via Aiven Postgres.

Lazy import of psycopg to avoid requiring it at module import time.
"""

import os
from typing import Any

from cleanroom.control.ops import Operator
from cleanroom.control.ops import OperatorContext
from cleanroom.control.registry.store import TaskRegistryStore
from cleanroom.fixtures import (
    CannedBenchmark,
    DummyProposer,
    InMemoryLogClient,
    NoOpPore,
)


class RealBenchmark:
    """Wrapper around the real benchmark module for use in dispatch_run.

    Adapts the real benchmark functions (run_benchmark, check_correctness,
    is_within_noise) from cleanroom.benchmark to match the CannedBenchmark
    interface so the loop can use either fixture or real benchmarks transparently.

    This is used only when CLEANROOM_PG_DSN is set (Phase-2 real backend).
    """

    def run_benchmark(
        self, conn, workload_id: str, *, warmup: int = 5, trials: int = 10
    ):
        """Execute the real frozen workload on a live Postgres connection.

        Delegates directly to cleanroom.benchmark.run_benchmark, which requires
        a real psycopg3 connection and measures actual database performance.

        Args:
            conn: An open psycopg3 connection (required; raises if None).
            workload_id: Key into the frozen workload registry.
            warmup: Untimed warmup iterations (default 5).
            trials: Sequentially-timed measurement iterations (default 10).

        Returns:
            Result(p99_ms, throughput, cost_estimate, samples).
        """
        from cleanroom.benchmark import run_benchmark as real_run_benchmark

        return real_run_benchmark(conn, workload_id, warmup=warmup, trials=trials)

    def check_correctness(self, conn, candidate):
        """Verify a candidate does not change query results (real gate).

        Delegates to cleanroom.benchmark.check_correctness, which handles
        query rewrites and verifies semantic equivalence.

        Args:
            conn: An open psycopg3 connection (or None in fixture mode).
            candidate: The candidate to validate.

        Returns:
            True if results are unchanged, False if a rewrite changed results.
        """
        from cleanroom.benchmark import check_correctness as real_check_correctness

        return real_check_correctness(conn, candidate)

    def is_within_noise(self, baseline_samples, candidate_samples):
        """Return True if the candidate is statistically indistinguishable from baseline.

        Delegates to cleanroom.benchmark.is_within_noise, which uses a Welch's t-test
        and minimum-effect-size floor to guard against noise.

        Args:
            baseline_samples: Baseline latency samples.
            candidate_samples: Candidate latency samples.

        Returns:
            True if within noise, False if the improvement is signal.
        """
        from cleanroom.benchmark import is_within_noise as real_is_within_noise

        return real_is_within_noise(baseline_samples, candidate_samples)


def make_run_store():
    """Select persistent or in-memory run store based on CLEANROOM_PG_DSN env var.

    Returns:
        SwappableRunStore: PgRunStore if DSN is set, InMemoryRunStore otherwise.
    """
    dsn = os.environ.get("CLEANROOM_PG_DSN")
    if dsn:
        # Lazy import to avoid requiring psycopg at module import time
        from cleanroom.control.dispatcher.pg_store import PgRunStore

        return PgRunStore.from_dsn(dsn)
    else:
        from cleanroom.control.dispatcher.store_interface import InMemoryRunStore

        return InMemoryRunStore()


def make_logclient():
    """Select persistent or in-memory logclient based on CLEANROOM_PG_DSN env var.

    If using Postgres backend, ensures schema tables exist (init_schema).

    Returns:
        LogClient: PgLogClient if DSN is set, InMemoryLogClient otherwise.
    """
    dsn = os.environ.get("CLEANROOM_PG_DSN")
    if dsn:
        # Lazy imports
        from cleanroom.control.dispatcher.pg_store import PgRunStore
        from cleanroom.db import connect, init_schema
        from cleanroom.logclient import PgLogClient

        # Open connection, init schema, create logclient
        # Note: we open a dedicated connection here; PgLogClient.from_dsn opens its own.
        # For init_schema, we just need a fresh connection to ensure tables exist.
        conn = connect(dsn)
        init_schema(conn)
        conn.close()

        # Now create the logclient with its own connection
        return PgLogClient.from_dsn(dsn)
    else:
        return InMemoryLogClient()


def make_operator() -> Operator:
    """Create an Operator with persistent or in-memory backends.

    Returns:
        Operator: Configured with TaskRegistryStore and selected run store.
    """
    registry = TaskRegistryStore()
    run_store = make_run_store()
    return Operator(registry, run_store)


def make_dispatch_ctx(logclient) -> OperatorContext:
    """Create OperatorContext for dispatch_run with real or fixture proposer/benchmark.

    Phase-2 swap: if CLEANROOM_PG_DSN is set, uses real proposer + benchmark.
    Otherwise defaults to FIXTURE proposer (DummyProposer) + benchmark (CannedBenchmark).

    Components:
      - proposer: ClaudeCodeProposer if DSN set, DummyProposer otherwise
      - benchmark: RealBenchmark if DSN set, CannedBenchmark otherwise
      - pore: REAL frozen pore (cleanroom.pore) — never swaps
      - logclient: Given (persistent or in-memory)

    Args:
        logclient: LogClient instance (PgLogClient or InMemoryLogClient).

    Returns:
        OperatorContext with the above components.
    """
    # Import the real pore module (frozen, do not modify)
    import cleanroom.pore

    dsn = os.environ.get("CLEANROOM_PG_DSN")
    if dsn:
        # Phase-2: Real proposer and benchmark (require live Postgres)
        from cleanroom.loop.proposers import ClaudeCodeProposer

        proposer = ClaudeCodeProposer()
        benchmark = RealBenchmark()
    else:
        # Phase-1: FIXTURE path (all existing tests use this)
        proposer = DummyProposer()
        benchmark = CannedBenchmark()

    return OperatorContext(
        proposer=proposer,
        benchmark=benchmark,
        pore=cleanroom.pore,
        logclient=logclient,
    )


def governance_pore() -> Any:
    """Return the REAL frozen pore module for task registration governance.

    Used by register_task to evaluate task_definition candidates against
    the frozen risk rules. Never swaps; always the real pore.

    Returns:
        The cleanroom.pore module.
    """
    import cleanroom.pore

    return cleanroom.pore
