"""Phase 3 integration — wire Story C's curves to Story B's real Postgres log.

Integration #2: C reads from A's real Postgres experiment log.
               Swap InMemoryLogClient → PgLogClient; the C functions are already
               backend-agnostic (they only call logclient.read_experiments()).

Integration #3: C injects proposers into A's run_loop to populate the model axis.
               run_model_axis_comparison() runs run_loop for each requested model
               and returns region_per_dollar() from the resulting logclient.

Quick-start (requires CLEANROOM_PG_DSN and psycopg[binary] + numpy installed):

    export CLEANROOM_PG_DSN="postgres://..."
    python3 -m cleanroom.integration

With real Claude proposers (also requires ANTHROPIC_API_KEY):

    from cleanroom.loop.proposers import ClaudeProposer
    from cleanroom.integration import connect_logclient, run_model_axis_comparison
    logclient = connect_logclient()
    run_model_axis_comparison(
        logclient,
        task_spec={"conn": db_conn, "workload_id": "default"},
        proposer_factory=lambda model: ClaudeProposer(model=model),
    )
"""

from cleanroom import db as _db
from cleanroom.logclient import PgLogClient  # noqa: F401 — re-exported for callers


class PoreModuleAdapter:
    """Wrap cleanroom.pore (module-level evaluate fn) as an object with .evaluate().

    run_loop calls pore.evaluate(candidate). Python's attribute lookup on a module
    already makes this work when you pass the module directly, but this explicit
    adapter documents the integration point and lets tests swap pore implementations.

    Story B's pore is a frozen, module-level function — not a class. This adapter
    bridges the two without touching either side's contract.
    """

    def __init__(self, pore_module=None):
        if pore_module is None:
            from cleanroom import pore as _pore
            pore_module = _pore
        self._pore = pore_module

    def evaluate(self, candidate):
        return self._pore.evaluate(candidate)


def connect_logclient(dsn: str | None = None) -> PgLogClient:
    """Open an Aiven Postgres connection, init the schema, and return a PgLogClient.

    Args:
        dsn: Connection string. Falls back to CLEANROOM_PG_DSN env var.

    Returns:
        PgLogClient backed by a live psycopg3 connection.
        Caller owns lifecycle — call logclient.close() when done.

    Raises:
        RuntimeError: If no DSN provided and CLEANROOM_PG_DSN is unset.
    """
    conn = _db.connect(dsn)
    _db.init_schema(conn)
    return PgLogClient(conn)


def seed_if_empty(logclient, *, n_per_drift: int = 20, seed_val: int = 42) -> int:
    """Seed synthetic experiments into logclient if it has no data yet.

    Uses the same seeder as Phase 0 (fixtures/seed_synthetic_log.py) so the
    Phase 3 dashboard can render even before A's real loop has produced data.
    Idempotent: returns 0 without writing if experiments already exist.

    Args:
        logclient: Any LogClient (InMemoryLogClient or PgLogClient).
        n_per_drift: Experiments per drift level (5 levels → 5*n_per_drift total).
        seed_val: Random seed for reproducibility.

    Returns:
        Number of experiments written (0 if logclient was non-empty).
    """
    if logclient.read_experiments():
        return 0
    from cleanroom.fixtures.seed_synthetic_log import seed
    seed(logclient, n_per_drift=n_per_drift, seed_val=seed_val)
    return len(logclient.read_experiments())


def run_model_axis_comparison(
    logclient,
    task_spec: dict,
    *,
    models: list | None = None,
    iterations: int = 5,
    proposer_factory=None,
    benchmark=None,
) -> list[dict]:
    """Run run_loop for each model and return the model axis comparison.

    This is integration #3: C injects proposers into A's run_loop so the model
    axis (region_per_dollar) is populated from real loop data.

    Args:
        logclient: Any LogClient — data lands here and is read for the axis.
        task_spec: Base task_spec; model and task_id are overridden per model.
        models: Model names to run. Defaults to ["haiku", "sonnet"].
        iterations: run_loop iterations per model.
        proposer_factory: Callable(model_name) -> proposer. Defaults to DummyProposer
            (no API key needed). Pass ``lambda m: ClaudeProposer(model=m)`` for
            real Claude runs (requires ANTHROPIC_API_KEY).
        benchmark: Benchmark adapter. Defaults to CannedBenchmark (no Postgres needed).
            Pass the real cleanroom.benchmark module for Aiven Postgres runs.

    Returns:
        list[dict] from region_per_dollar(logclient) after all model runs complete.
    """
    from cleanroom.loop import run_loop
    from cleanroom.fixtures import CannedBenchmark, DummyProposer
    from cleanroom.modelaxis import region_per_dollar

    if models is None:
        models = ["haiku", "sonnet"]
    if benchmark is None:
        benchmark = CannedBenchmark(baseline_p99=100.0)
    pore = PoreModuleAdapter()

    for model in models:
        proposer = proposer_factory(model) if proposer_factory else DummyProposer()
        spec = {**task_spec, "model": model, "task_id": f"phase3-axis-{model}"}
        run_loop(
            task_spec=spec,
            proposer=proposer,
            benchmark=benchmark,
            pore=pore,
            logclient=logclient,
            iterations=iterations,
        )

    return region_per_dollar(logclient)


def live_dashboard(
    dsn: str | None = None,
    *,
    task_id: str | None = None,
    seed_if_no_data: bool = True,
) -> str:
    """Connect to Postgres, optionally seed synthetic data, and render the dashboard.

    This is the one-liner entry point for Phase 3: it wires integration #2 (real
    Postgres logclient) and renders all three Story C panels (spatial curve,
    longitudinal curve, model axis) from live data.

    Args:
        dsn: Connection string. Falls back to CLEANROOM_PG_DSN env var.
        task_id: Filter dashboard to a specific task (None = all experiments).
        seed_if_no_data: If the DB is empty, seed synthetic experiments so the
            dashboard always renders something useful for demos and CI checks.

    Returns:
        Rendered ASCII dashboard string (same as render() in Phase 0).
    """
    from cleanroom.dashboard import render

    logclient = connect_logclient(dsn)
    try:
        if seed_if_no_data:
            n_seeded = seed_if_empty(logclient)
            if n_seeded:
                print(f"[integration] seeded {n_seeded} synthetic experiments into Postgres")
        return render(logclient, task_id)
    finally:
        logclient.close()


if __name__ == "__main__":
    import sys

    print("[phase3] connecting to Postgres…")
    try:
        out = live_dashboard(seed_if_no_data=True)
        print(out)
    except RuntimeError as exc:
        print(f"[phase3] ERROR: {exc}", file=sys.stderr)
        print(
            "[phase3] Set CLEANROOM_PG_DSN and run again, or run the Phase-0 demo:\n"
            "  PYTHONPATH=. python3 cleanroom/fixtures/seed_synthetic_log.py",
            file=sys.stderr,
        )
        sys.exit(1)
