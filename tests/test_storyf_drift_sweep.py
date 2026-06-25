"""Story F (#16) — offline tests for the drift sweep + frozen stationarity tripwire.

No DB: the stationarity proxy pore, the drift workload generator, and the full
sweep against CannedBenchmark + InMemoryLogClient producing a rising spatial curve
via the existing boundary analysis.
"""

from cleanroom.boundary import escalation_rate_by_drift
from cleanroom.fixtures import CannedBenchmark, InMemoryLogClient
from cleanroom.pore import evaluate as base_evaluate
from cleanroom.pore.stationarity import DEFAULT_THRESHOLD, StationarityProxyPore
from cleanroom.types import Candidate
from scripts.drift_sweep import DRIFT_LEVELS, drifted_workload_sql, run_sweep


# --- the frozen stationarity tripwire ---------------------------------------

def test_above_threshold_escalates_any_candidate():
    safe = Candidate(type="index", params={"table": "t", "columns": ["c"]}, reversible=True)
    pore = StationarityProxyPore(drift_level=0.9)
    res = pore.evaluate(safe)
    assert res.requires_human_judgment is True
    assert res.decision == "escalate" and res.pore == "stationarity_proxy"


def test_at_or_below_threshold_defers_to_base_gate():
    safe = Candidate(type="index", params={"table": "t", "columns": ["c"]}, reversible=True)
    pore = StationarityProxyPore(drift_level=0.5)  # 0.5 is NOT > 0.5 -> trusted region
    assert pore.evaluate(safe) == base_evaluate(safe)  # identical to base -> auto_safe
    assert pore.evaluate(safe).requires_human_judgment is False


def test_below_threshold_still_catches_irreversible_via_base_gate():
    risky = Candidate(type="migration", params={"op": "drop"}, reversible=False)
    pore = StationarityProxyPore(drift_level=0.1)
    # base gate still fires on irreversibility even inside the trusted region
    assert pore.evaluate(risky).requires_human_judgment is True
    assert pore.evaluate(risky).pore == "reversibility"


def test_threshold_is_a_constant_default():
    assert DEFAULT_THRESHOLD == 0.5
    assert StationarityProxyPore(drift_level=0.0).threshold == 0.5


# --- the drift workload generator -------------------------------------------

def test_workload_window_widens_with_drift():
    import re
    def window(sql):
        return int(re.search(r"interval '(\d+) days'", sql).group(1))
    assert window(drifted_workload_sql(0.0)) < window(drifted_workload_sql(1.0))


def test_offindex_predicates_appear_with_drift():
    assert "status" not in drifted_workload_sql(0.0)
    assert "status = 'pending'" in drifted_workload_sql(0.5)
    assert "amount > 10" in drifted_workload_sql(0.75)


# --- the full sweep -> a rising spatial curve -------------------------------

def test_sweep_produces_rising_curve():
    logclient = InMemoryLogClient()
    run_sweep(logclient=logclient, benchmark=CannedBenchmark(), conn=None,
              threshold=DEFAULT_THRESHOLD, iterations=4, register=False, verbose=False)
    curve = {row["drift_level"]: row["escalation_rate"] for row in escalation_rate_by_drift(logclient)}
    # >=5 distinct drift levels logged
    assert set(curve) == set(DRIFT_LEVELS)
    # flat-zero inside the trusted region, 100% above the frozen threshold
    assert curve[0.0] == 0.0 and curve[0.25] == 0.0 and curve[0.5] == 0.0
    assert curve[0.75] == 1.0 and curve[1.0] == 1.0
    # monotonic non-decreasing -> the curve rises with drift
    rates = [curve[d] for d in DRIFT_LEVELS]
    assert rates == sorted(rates)


def test_sweep_logs_escalations_with_crossings():
    logclient = InMemoryLogClient()
    run_sweep(logclient=logclient, benchmark=CannedBenchmark(), conn=None,
              threshold=DEFAULT_THRESHOLD, iterations=4, register=False, verbose=False)
    escalated = [e for e in logclient.read_experiments() if e["decision"] == "escalated"]
    assert escalated and all(e["drift_level"] > DEFAULT_THRESHOLD for e in escalated)
    # every escalation has a crossing row (the audit trail)
    assert len(logclient.read_crossings()) == len(escalated)
