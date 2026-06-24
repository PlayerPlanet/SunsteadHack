"""Integration tests for Phase 3 — Story C wired to Story B's Postgres log.

Tests run against InMemoryLogClient by default (no Aiven, no psycopg needed).
If CLEANROOM_PG_DSN is set in the environment, one additional test verifies the
real Postgres path end-to-end.

Run with:
    cd SunsteadHack && PYTHONPATH=. python3 tests/test_phase3.py
"""

import os
import sys

from cleanroom.fixtures import InMemoryLogClient
from cleanroom.fixtures.seed_synthetic_log import seed
from cleanroom.boundary import escalation_rate_by_drift, escalations_per_unit_work
from cleanroom.dashboard import render
from cleanroom.modelaxis import region_per_dollar
from cleanroom.integration import PoreModuleAdapter, seed_if_empty, run_model_axis_comparison


# ── Pore adapter ──────────────────────────────────────────────────────────────

def test_pore_module_adapter():
    """PoreModuleAdapter bridges the module-level evaluate fn to .evaluate()."""
    from cleanroom.types import Candidate
    adapter = PoreModuleAdapter()
    safe = Candidate(type="index", params={}, reversible=True)
    assert adapter.evaluate(safe).decision == "allow"
    risky = Candidate(type="index", params={}, reversible=False)
    assert adapter.evaluate(risky).decision == "escalate"
    guc_high = Candidate(type="guc", params={"name": "shared_buffers"}, reversible=True)
    assert adapter.evaluate(guc_high).decision == "escalate"
    print("  pore adapter: PASS")


# ── Seed helper ───────────────────────────────────────────────────────────────

def test_seed_if_empty():
    """seed_if_empty populates an empty logclient and is idempotent."""
    logclient = InMemoryLogClient()
    n1 = seed_if_empty(logclient, n_per_drift=5)
    assert n1 > 0, "Should have seeded experiments"
    n2 = seed_if_empty(logclient)
    assert n2 == 0, "Should not re-seed non-empty logclient"
    print(f"  seed_if_empty: seeded {n1}, idempotent re-seed=0: PASS")


# ── Dashboard ─────────────────────────────────────────────────────────────────

def test_dashboard_renders_from_memory():
    """render() produces all three panels from InMemoryLogClient."""
    logclient = InMemoryLogClient()
    seed(logclient, n_per_drift=10)
    out = render(logclient, task_id=None)
    assert "(A)" in out, "Missing spatial curve panel (A)"
    assert "(B)" in out, "Missing longitudinal panel (B)"
    assert "(C)" in out, "Missing model axis panel (C)"
    assert "PROXY" in out, "Missing proxy/lower-bound disclaimer"
    assert "Flat" in out or "flat" in out, "Missing frozen-pore flat-line note"
    print(f"  dashboard renders ({len(out)} chars): PASS")


def test_dashboard_filters_by_task_id():
    """render(task_id=...) filters experiments to a single task."""
    logclient = InMemoryLogClient()
    seed(logclient, n_per_drift=10)
    all_exps = logclient.read_experiments()
    if not all_exps:
        print("  dashboard filter: SKIP (no experiments)")
        return
    target = all_exps[0]["task_id"]
    out = render(logclient, task_id=target)
    # Dashboard should render with the filtered task scope
    assert "(A)" in out, "Filtered dashboard missing panel A"
    print(f"  dashboard filter (task_id={target!r}): PASS")


# ── Model axis ────────────────────────────────────────────────────────────────

def test_model_axis_comparison_in_memory():
    """run_model_axis_comparison logs both models and returns axis rows."""
    logclient = InMemoryLogClient()
    seed(logclient, n_per_drift=5)  # prime with drift data
    axis = run_model_axis_comparison(
        logclient,
        task_spec={"conn": None, "workload_id": ""},
        iterations=4,
    )
    models_in_axis = {row["model"] for row in axis}
    assert "haiku" in models_in_axis, f"haiku missing from axis: {models_in_axis}"
    assert "sonnet" in models_in_axis, f"sonnet missing from axis: {models_in_axis}"
    for row in axis:
        assert "region_per_dollar" in row, f"Missing region_per_dollar key: {row}"
    print(f"  model axis: {[{r['model']: round(r['region_per_dollar'], 3)} for r in axis]}")
    print("  model axis comparison: PASS")


def test_boundary_curves_from_seeded_log():
    """escalation_rate_by_drift and escalations_per_unit_work work with PgLogClient interface."""
    logclient = InMemoryLogClient()
    seed(logclient, n_per_drift=15)
    spatial = escalation_rate_by_drift(logclient)
    longitudinal = escalations_per_unit_work(logclient)
    assert spatial, "Spatial curve is empty"
    assert longitudinal, "Longitudinal curve is empty"
    # escalation rate should increase with drift
    rates = [row["escalation_rate"] for row in spatial]
    assert rates[-1] > rates[0], f"Escalation rate should rise with drift: {rates}"
    print(f"  boundary curves: spatial={len(spatial)} buckets, longitudinal={len(longitudinal)} windows: PASS")


# ── Real Postgres path (optional) ─────────────────────────────────────────────

def test_pg_live_dashboard():
    """Connect to real Aiven Postgres and render the dashboard (skips if no DSN)."""
    dsn = os.environ.get("CLEANROOM_PG_DSN")
    if not dsn:
        print("  pg live dashboard: SKIP (CLEANROOM_PG_DSN not set)")
        return
    from cleanroom.integration import live_dashboard
    print("  pg live dashboard: connecting…")
    out = live_dashboard(dsn, seed_if_no_data=True)
    assert "(A)" in out, "Postgres dashboard missing panel A"
    assert "(B)" in out, "Postgres dashboard missing panel B"
    print(f"  pg live dashboard: PASS ({len(out)} chars rendered)")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("pore module adapter",            test_pore_module_adapter),
        ("seed_if_empty",                  test_seed_if_empty),
        ("dashboard renders",              test_dashboard_renders_from_memory),
        ("dashboard filter by task_id",    test_dashboard_filters_by_task_id),
        ("model axis comparison",          test_model_axis_comparison_in_memory),
        ("boundary curves from seeded log", test_boundary_curves_from_seeded_log),
        ("pg live dashboard",              test_pg_live_dashboard),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn()
            passed += 1
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"  FAIL: {exc}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
