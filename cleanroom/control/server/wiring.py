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

import os
from typing import Any

from cleanroom.control.ops import Operator, OperatorContext
from cleanroom.control.registry.store import TaskRegistryStore
from cleanroom.fixtures import CannedBenchmark, DummyProposer, InMemoryLogClient

# Process-level singletons (see module docstring). Keyed implicitly by process; a
# fresh process (e.g. each CLI invocation) starts with these as None.
_operator: Operator | None = None
_logclient: Any = None


def reset_caches() -> None:
    """Clear the cached singletons. For tests that flip CLEANROOM_PG_DSN."""
    global _operator, _logclient
    _operator = None
    _logclient = None


def _make_run_store():
    """Build the run store for the current CLEANROOM_PG_DSN (no caching)."""
    dsn = os.environ.get("CLEANROOM_PG_DSN")
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

    dsn = os.environ.get("CLEANROOM_PG_DSN")
    if dsn:
        from cleanroom.db import connect, init_schema
        from cleanroom.logclient import PgLogClient

        # Ensure the log tables exist, then hand the client its own connection.
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


def make_dispatch_ctx(logclient) -> OperatorContext:
    """OperatorContext for dispatch_run.

    Phase 1 uses the FIXTURE proposer + benchmark (no live workload DB needed) but
    the REAL frozen pore and the given (persistent or in-memory) logclient. Phase 2
    swaps in A's ClaudeCodeProposer + B's real benchmark behind this same seam.
    """
    import cleanroom.pore

    return OperatorContext(
        proposer=DummyProposer(),
        benchmark=CannedBenchmark(),
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
