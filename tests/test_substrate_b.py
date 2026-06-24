"""Story B (issue #3) substrate tests — benchmark stats, correctness, pore, logclient.

Covers the Definition of Done that does not require a live database:
  * `is_within_noise` provably REJECTS within-variance changes and ACCEPTS real wins.
  * `check_correctness` catches a result-changing rewrite (via a fake conn).
  * the frozen pore escalates on irreversible / high-blast / claim-surface and
    allows otherwise.
  * `PgLogClient` writes the correct SQL/params against a fake conn, and round-trips
    rows in the same dict shape as the in-memory fixture.

Live-DB integration (run_benchmark timing, real INSERTs) is exercised separately in
the e2e path when CLEANROOM_PG_DSN is set; these tests stay hermetic.
"""

import numpy as np
import pytest

from cleanroom.benchmark import check_correctness, is_within_noise, run_benchmark
from cleanroom.pore import evaluate
from cleanroom.types import Candidate


# --------------------------------------------------------------------------- #
# is_within_noise — Gate-2 guard                                              #
# --------------------------------------------------------------------------- #

class TestIsWithinNoise:
    def test_identical_samples_are_within_noise(self):
        s = [100.0, 101.0, 99.0, 100.5, 100.2]
        assert is_within_noise(s, s) is True

    def test_tiny_improvement_within_floor_is_noise(self):
        # ~1% median improvement — below the 2% effect floor => noise.
        rng = np.random.default_rng(0)
        base = list(100.0 + rng.normal(0, 6.5, 30))
        cand = list(99.0 + rng.normal(0, 6.5, 30))
        assert is_within_noise(base, cand) is True

    def test_large_consistent_improvement_is_signal(self):
        # ~40% improvement, low variance => clearly NOT within noise.
        rng = np.random.default_rng(1)
        base = list(100.0 + rng.normal(0, 5.0, 30))
        cand = list(60.0 + rng.normal(0, 5.0, 30))
        assert is_within_noise(base, cand) is False

    def test_large_mean_shift_buried_in_huge_variance_is_noise(self):
        # Median clears the 2% floor, but variance is so large the t-test cannot
        # distinguish the two => correctly reported as within noise.
        rng = np.random.default_rng(2)
        base = list(100.0 + rng.normal(0, 80.0, 30))
        cand = list(85.0 + rng.normal(0, 80.0, 30))
        assert is_within_noise(base, cand) is True

    def test_regression_is_not_a_win(self):
        # Candidate is SLOWER — not a real win, reported as within-noise.
        base = [100.0] * 10
        cand = [130.0] * 10
        assert is_within_noise(base, cand) is True

    def test_empty_inputs_are_within_noise(self):
        assert is_within_noise([], [100.0]) is True
        assert is_within_noise([100.0], []) is True


# --------------------------------------------------------------------------- #
# check_correctness — Gate-4                                                   #
# --------------------------------------------------------------------------- #

class _FakeCursor:
    """Minimal cursor that returns canned rows keyed by SQL substring."""

    def __init__(self, responses):
        self._responses = responses
        self.description = [("col",)]
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._rows = self._responses.get(sql, [])

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, responses):
        self._responses = responses

    def cursor(self):
        return _FakeCursor(self._responses)


def test_check_correctness_passes_for_index_candidate():
    # Index changes can never alter results -> True without touching the DB.
    cand = Candidate(type="index", params={"table": "t", "columns": ["a"]}, reversible=True)
    assert check_correctness(None, cand) is True


def test_check_correctness_catches_result_changing_rewrite():
    orig = "SELECT * FROM t WHERE a = 1"
    bad = "SELECT * FROM t WHERE a = 2"  # different result set
    conn = _FakeConn({orig: [(1,), (2,)], bad: [(3,)]})
    cand = Candidate(
        type="rewrite",
        params={"original_sql": orig, "rewritten_sql": bad},
        reversible=True,
    )
    assert check_correctness(conn, cand) is False


def test_check_correctness_accepts_equivalent_rewrite():
    orig = "SELECT a FROM t ORDER BY a"
    good = "SELECT a FROM t ORDER BY a /* hint */"
    conn = _FakeConn({orig: [(1,), (2,)], good: [(1,), (2,)]})
    cand = Candidate(
        type="rewrite",
        params={"original_sql": orig, "rewritten_sql": good},
        reversible=True,
    )
    assert check_correctness(conn, cand) is True


# --------------------------------------------------------------------------- #
# pore — frozen escalation gate                                               #
# --------------------------------------------------------------------------- #

class TestPore:
    def test_reversible_safe_candidate_is_allowed(self):
        cand = Candidate(type="index", params={"table": "t", "columns": ["a"]}, reversible=True)
        r = evaluate(cand)
        assert r.requires_human_judgment is False
        assert r.decision == "allow"
        assert r.risk_level == "low"

    def test_irreversible_candidate_escalates(self):
        cand = Candidate(type="partition", params={}, reversible=False)
        r = evaluate(cand)
        assert r.requires_human_judgment is True
        assert r.decision == "escalate"
        assert r.pore == "reversibility"

    def test_high_blast_radius_guc_escalates(self):
        cand = Candidate(type="guc", params={"name": "shared_buffers", "value": "4GB"}, reversible=True)
        r = evaluate(cand)
        assert r.requires_human_judgment is True
        assert r.pore == "blast_radius"

    def test_explicit_high_blast_marker_escalates(self):
        cand = Candidate(type="index", params={"blast_radius": "high"}, reversible=True)
        assert evaluate(cand).requires_human_judgment is True

    def test_claim_surface_escalates(self):
        cand = Candidate(type="rewrite", params={"touches_claim_surface": True}, reversible=True)
        r = evaluate(cand)
        assert r.requires_human_judgment is True
        assert r.pore == "claim_surface"

    def test_low_blast_guc_is_allowed(self):
        cand = Candidate(type="guc", params={"name": "work_mem", "value": "64MB"}, reversible=True)
        assert evaluate(cand).requires_human_judgment is False

    def test_pore_is_pure_no_side_effects(self):
        # Same input -> same output, twice (frozen, deterministic).
        cand = Candidate(type="index", params={"table": "t", "columns": ["a"]}, reversible=True)
        assert evaluate(cand) == evaluate(cand)


# --------------------------------------------------------------------------- #
# run_benchmark — guard rails (no live DB)                                     #
# --------------------------------------------------------------------------- #

def test_run_benchmark_requires_real_conn():
    with pytest.raises(ValueError, match="conn is None"):
        run_benchmark(None, "__default__", warmup=1, trials=1)


def test_run_benchmark_rejects_unknown_workload():
    # A made-up workload id should fail loudly rather than silently measure nothing.
    class _C:
        def cursor(self):  # pragma: no cover - should never be reached
            raise AssertionError("should fail before opening a cursor")

    with pytest.raises(ValueError, match="unknown workload_id"):
        run_benchmark(_C(), "does-not-exist", warmup=1, trials=1)


# --------------------------------------------------------------------------- #
# PgLogClient — SQL/params shape against a recording fake conn                 #
# --------------------------------------------------------------------------- #

class _RecordingCursor:
    def __init__(self, store):
        self._store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._store["last_sql"] = sql
        self._store["last_params"] = params

    def fetchone(self):
        return (42,)


class _RecordingConn:
    def __init__(self):
        self.store = {}
        self.commits = 0

    def cursor(self):
        return _RecordingCursor(self.store)

    def commit(self):
        self.commits += 1


def test_pglogclient_write_experiment_returns_id_and_commits():
    pytest.importorskip("psycopg")
    from cleanroom.logclient import PgLogClient

    conn = _RecordingConn()
    client = PgLogClient(conn)
    exp_id = client.write_experiment(
        task_id="t", model="m", drift_level=0.0, candidate={"type": "index"},
        baseline_p99=100.0, candidate_p99=90.0, cost_estimate=1.0,
        correctness_ok=True, within_noise=False, decision="keep",
    )
    assert exp_id == 42
    assert conn.commits == 1
    assert "INSERT INTO experiment" in conn.store["last_sql"]


def test_pglogclient_read_experiments_rejects_unknown_filter_column():
    pytest.importorskip("psycopg")
    from cleanroom.logclient import PgLogClient

    client = PgLogClient(_RecordingConn())
    with pytest.raises(ValueError, match="unknown filter column"):
        client.read_experiments({"not_a_column": 1})
