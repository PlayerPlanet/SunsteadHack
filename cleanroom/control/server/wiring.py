"""Backend factory — centralized persistent-vs-inmemory selection for Story D Phase 1.

This module is the single point where both the CLI and MCP adapters select storage
backends based on the `CLEANROOM_PG_DSN` environment variable:

  * DSN set  -> Aiven Postgres: PgRunStore + PgLogClient. State persists across
    separate processes (so a Claude plugin's slash commands, each its own process,
    share one governance log + run store). This is what makes Aiven load-bearing
    for the control plane.
  * DSN unset -> in-memory fixtures. State lives only within a single process. The
    long-lived MCP server still works across tool calls (the stores are cached
    process-singletons below), but separate CLI invocations will NOT see each
    other's state — that's the whole reason the Aiven backend exists.

The stores are cached as process-level singletons so that, within one process,
every operator call shares the SAME run store / logclient / Operator (and thus the
same cancel-event registry). Without this, each tool call would get a fresh empty
in-memory store and a multi-step flow (register -> pending -> adjudicate) could
never see its own prior writes. Call `reset_caches()` in tests to clear them.

psycopg is imported lazily so importing this module never requires it.
"""

import logging
import os
from typing import Any

from cleanroom.control.ops import Operator, OperatorContext
from cleanroom.control.registry.store import TaskRegistryStore
from cleanroom.fixtures import CannedBenchmark, DummyProposer, InMemoryLogClient

logger = logging.getLogger(__name__)

# Process-level singletons (see module docstring). Keyed implicitly by process; a
# fresh process (e.g. each CLI invocation) starts with these as None.
_operator: Operator | None = None
_logclient: Any = None
_secret_dsn_cache: str | None = None
_secret_dsn_fetched: bool = False


def reset_caches() -> None:
    """Clear the cached singletons. For tests that flip CLEANROOM_PG_DSN."""
    global _operator, _logclient, _secret_dsn_cache, _secret_dsn_fetched
    _operator = None
    _logclient = None
    _secret_dsn_cache = None
    _secret_dsn_fetched = False


def _secret_dsn() -> str | None:
    """Fetch the app DSN from AWS Secrets Manager when CLEANROOM_PG_SECRET_ID is set.

    The AgentCore-hosted runtime uses this: its IAM role grants
    secretsmanager:GetSecretValue on the secret, so the DSN is never stored in
    agentcore.json (whose envVars are plaintext-only) or committed to git. boto3 is
    imported lazily so the package imports without it outside the runtime. Cached for
    the process so we hit Secrets Manager once.
    """
    global _secret_dsn_cache, _secret_dsn_fetched
    if _secret_dsn_fetched:
        return _secret_dsn_cache
    sid = os.environ.get("CLEANROOM_PG_SECRET_ID") or os.environ.get("CLEANROOM_PG_SECRET_ARN")
    if sid:
        import boto3

        kwargs = {"region_name": os.environ["AWS_REGION"]} if os.environ.get("AWS_REGION") else {}
        resp = boto3.client("secretsmanager", **kwargs).get_secret_value(SecretId=sid)
        val = resp.get("SecretString")
        # Strip — a DSN stored from a file often carries a trailing newline, which
        # would otherwise break the psycopg connection string.
        _secret_dsn_cache = val.strip() if val else val
    _secret_dsn_fetched = True
    return _secret_dsn_cache


def data_dsn() -> str | None:
    """DSN the data path (run store + logclient) uses.

    Order: CLEANROOM_PG_APP_DSN (non-superuser app login, remote deploy) ->
    CLEANROOM_PG_DSN (local/stdio) -> a Secrets Manager fetch if CLEANROOM_PG_SECRET_ID
    is set (the AgentCore runtime). None of these set -> in-memory backend.
    """
    return (os.environ.get("CLEANROOM_PG_APP_DSN")
            or os.environ.get("CLEANROOM_PG_DSN")
            or _secret_dsn())


def _external_migrations() -> bool:
    """True when schema creation is owned by an out-of-band admin migration.

    In a deployment the serving login is a non-superuser that lacks CREATE, and the
    schema/roles are applied separately (sql/, the migrate step). Don't try to
    init_schema from the serving process then. Triggered by serving via the app DSN,
    a Secrets Manager DSN, or an explicit CLEANROOM_SKIP_SCHEMA_INIT flag.
    """
    return bool(os.environ.get("CLEANROOM_PG_APP_DSN")
                or os.environ.get("CLEANROOM_PG_SECRET_ID")
                or os.environ.get("CLEANROOM_PG_SECRET_ARN")
                or os.environ.get("CLEANROOM_SKIP_SCHEMA_INIT"))


def _make_run_store():
    """Build the run store for the current data DSN (no caching)."""
    dsn = data_dsn()
    if dsn:
        from cleanroom.control.dispatcher.pg_store import PgRunStore

        return PgRunStore.from_dsn(dsn)
    from cleanroom.control.dispatcher.store_interface import InMemoryRunStore

    return InMemoryRunStore()


def make_logclient():
    """Return the (cached) logclient: PgLogClient if DSN set, else InMemoryLogClient.

    For the Postgres backend, the frozen experiment/crossing/judgment schema is
    ensured once via init_schema before the client is created.
    """
    global _logclient
    if _logclient is not None:
        return _logclient

    dsn = data_dsn()
    if dsn:
        from cleanroom.db import connect, init_schema
        from cleanroom.logclient import PgLogClient

        # Ensure the log tables exist — unless an admin owns migrations out-of-band
        # (deployment: the serving login is a non-superuser without CREATE).
        if not _external_migrations():
            conn = connect(dsn)
            try:
                init_schema(conn)
            finally:
                conn.close()
        _logclient = PgLogClient.from_dsn(dsn)
    else:
        _logclient = InMemoryLogClient()
    return _logclient


def make_operator() -> Operator:
    """Return the (cached) Operator wired to the selected run store.

    The TaskRegistryStore is JSON-file-backed and already cross-process persistent;
    the run store follows the CLEANROOM_PG_DSN selection above.
    """
    global _operator
    if _operator is None:
        _operator = Operator(TaskRegistryStore(), _make_run_store())
    return _operator


class RealBenchmark:
    """Wrapper around the real benchmark module for use in dispatch_run.

    Adapts the real benchmark functions (run_benchmark, check_correctness,
    is_within_noise) from cleanroom.benchmark to match the CannedBenchmark
    interface so the loop can use either fixture or real benchmarks transparently.

    Used only when a real Postgres backend is configured (data_dsn() set).
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


def make_dispatch_ctx(logclient) -> OperatorContext:
    """OperatorContext for dispatch_run.

    Phase 1 uses the FIXTURE proposer + benchmark (no live workload DB needed) but
    the REAL frozen pore and the given (persistent or in-memory) logclient. Phase 2
    swaps in A's ClaudeCodeProposer + B's real benchmark behind this same seam when a
    real Postgres backend is configured (data_dsn() set).
    """
    import cleanroom.pore

    if data_dsn():
        # Phase-2: real proposer + benchmark (require a live Postgres workload DB).
        from cleanroom.loop.proposers import ClaudeCodeProposer

        proposer = ClaudeCodeProposer()
        benchmark = RealBenchmark()
    else:
        # Phase-1: FIXTURE path (all existing tests use this).
        proposer = DummyProposer()
        benchmark = CannedBenchmark()

    return OperatorContext(
        proposer=proposer,
        benchmark=benchmark,
        pore=cleanroom.pore,
        logclient=logclient,
    )


def governance_pore() -> Any:
    """Return the REAL frozen pore module used to gate task registration.

    register_task evaluates a `task_definition` candidate against these frozen
    rules — that is what makes 'defining' a task governed. Never swapped.
    """
    import cleanroom.pore

    return cleanroom.pore


# ==================== Deployment-grade serving (Story G) ======================
#
# Two DSNs with different privilege levels:
#   * CLEANROOM_PG_DSN      — the admin/superuser login. Used ONLY for migrations
#     and schema init (init_schema), never to serve requests.
#   * CLEANROOM_PG_APP_DSN  — the non-superuser `sunstead_app` login the remote
#     server authenticates as; it SET ROLEs per request (see roles.py / sql/roles.sql).
#
# The stdio/local mode (a single trusted operator on their own machine) keeps using
# the admin DSN — there is no untrusted caller to wall off. The remote HTTP mode
# MUST use the app DSN and is guarded below.


def serving_dsn() -> str | None:
    """DSN the request-serving path uses (same as the data path)."""
    if not os.environ.get("CLEANROOM_PG_APP_DSN") and os.environ.get("CLEANROOM_PG_DSN"):
        logger.warning(
            "CLEANROOM_PG_APP_DSN unset — serving via CLEANROOM_PG_DSN. In production "
            "this should be the non-superuser sunstead_app login (see sql/roles.sql)."
        )
    return data_dsn()


def assert_serving_safe() -> None:
    """Boot guard for the remote server: refuse to serve as a Postgres superuser.

    No-op when there is no serving DSN (pure in-memory dev mode — nothing to wall off).
    Called from the HTTP entrypoint before binding the port, so an over-privileged
    deployment fails fast and loud rather than silently defeating the truth boundary.
    """
    dsn = serving_dsn()
    if not dsn:
        return
    from cleanroom.control.server.roles import assert_not_superuser
    from cleanroom.db import connect

    conn = connect(dsn)
    try:
        assert_not_superuser(conn)
    finally:
        conn.close()
