"""Deep boundary probe — offline tests (no API, no DB).

Covers: drift schedules, regime context, modeled measurement determinism, the
three boundary/calibration analyses, the per-style loop with mock actors, and the
two LLM agents driven by a fake Anthropic client (incl. backoff retry).
"""

import types

import pytest

from cleanroom.probe import (
    DRIFT_STYLES,
    ProbeRecord,
    baseline_samples,
    calibration_gap,
    drift_schedule,
    longitudinal_curve,
    modeled_samples,
    regime_context,
    regime_tier,
    spatial_curve,
)
from cleanroom.probe.agents import (
    HaikuOptimizerAgent,
    SonnetHumanAgent,
    _with_backoff,
)
from cleanroom.types import Candidate
from scripts.run_deep_probe import MockHuman, MockOptimizer, run_style


# --- drift schedules --------------------------------------------------------

@pytest.mark.parametrize("style", DRIFT_STYLES)
def test_schedule_length_and_range(style):
    sched = drift_schedule(style, 24)
    assert len(sched) == 24
    assert all(0.0 <= d <= 1.0 for d in sched)


def test_stationary_is_flat():
    sched = drift_schedule("stationary", 16)
    assert len(set(sched)) == 1  # constant -> the longitudinal-flat reference


def test_linear_ramp_spans_zero_to_one():
    sched = drift_schedule("linear_ramp", 11)
    assert sched[0] == 0.0 and sched[-1] == 1.0
    assert sched == sorted(sched)  # monotonic


def test_step_shock_has_two_levels_with_a_jump():
    sched = drift_schedule("step_shock", 10)
    assert set(sched) == {0.10, 0.90}
    assert sched[0] == 0.10 and sched[-1] == 0.90


def test_burst_is_mostly_calm_with_spikes():
    sched = drift_schedule("burst", 20)
    spikes = [d for d in sched if d >= 0.85]
    assert 1 <= len(spikes) <= 6
    assert sum(1 for d in sched if d < 0.3) > len(spikes)


def test_unknown_style_raises():
    with pytest.raises(ValueError, match="unknown drift style"):
        drift_schedule("nope", 5)


# --- regime context ---------------------------------------------------------

def test_regime_tiers_escalate_with_drift():
    assert regime_tier(0.1) == "calm"
    assert regime_tier(0.45) == "shifting"
    assert regime_tier(0.7) == "turbulent"
    assert regime_tier(0.95) == "regime_break"


def test_regime_context_shape():
    ctx = regime_context(0.9)
    assert ctx["regime"] == "regime_break"
    assert "schema" in ctx and "slow_queries" in ctx and ctx["drift"] == 0.9


# --- modeled measurement ----------------------------------------------------

def test_modeled_samples_deterministic():
    c = Candidate("index", {"table": "cast_info", "columns": ["movie_id"]}, True)
    a = modeled_samples(c, 0.2, 120.0, 3)
    b = modeled_samples(c, 0.2, 120.0, 3)
    assert a == b  # reproducible world


def test_index_effect_decays_with_drift():
    c = Candidate("index", {"table": "t", "columns": ["x"]}, True)
    import numpy as np
    calm = float(np.median(modeled_samples(c, 0.0, 120.0, 0)))
    drifted = float(np.median(modeled_samples(c, 0.9, 120.0, 0)))
    assert calm < drifted  # the same index helps less as the world drifts


def test_baseline_samples_deterministic():
    assert baseline_samples(120.0) == baseline_samples(120.0)


# --- analyses ---------------------------------------------------------------

def _rec(style, i, drift, escalated, human=None):
    return ProbeRecord(
        style=style, iteration=i, drift=drift, regime=regime_tier(drift),
        model="m", candidate={"type": "index"}, proposer_reasoning="", pore="x",
        risk_level="high" if escalated else "low", escalated=escalated,
        human_decision=human, decision="escalated" if escalated else "keep",
    )


def test_spatial_curve_buckets_and_rates():
    recs = [_rec("s", 0, 0.1, False), _rec("s", 1, 0.1, False),
            _rec("s", 2, 0.9, True), _rec("s", 3, 0.9, True)]
    curve = {row["drift"]: row for row in spatial_curve(recs)}
    assert curve[0.1]["escalation_rate"] == 0.0
    assert curve[0.9]["escalation_rate"] == 1.0


def test_longitudinal_tracks_order():
    recs = [_rec("s", i, 0.1, False) for i in range(4)] + [_rec("s", i, 0.9, True) for i in range(4, 8)]
    curve = longitudinal_curve(recs, window=4)
    assert curve[0]["ratio"] == 0.0 and curve[1]["ratio"] == 1.0


def test_calibration_gap_splits_approve_reject():
    recs = [_rec("s", 0, 0.9, True, human="approve"),
            _rec("s", 1, 0.9, True, human="reject"),
            _rec("s", 2, 0.9, True, human="reject")]
    gap = calibration_gap(recs)
    assert gap["n_escalated"] == 3
    assert gap["human_approved"] == 1 and gap["human_rejected"] == 2
    assert gap["false_stop_rate"] == pytest.approx(1 / 3)
    assert gap["pore_precision"] == pytest.approx(2 / 3)


# --- the per-style loop with mock actors ------------------------------------

def test_run_style_stationary_no_escalation():
    recs = run_style("stationary", 10, MockOptimizer(), MockHuman(), verbose=False)
    assert len(recs) == 10
    assert all(not r.escalated for r in recs)  # calm world -> safe proposals -> flat


def test_run_style_regime_break_escalates_and_is_judged():
    recs = run_style("step_shock", 12, MockOptimizer(), MockHuman(), verbose=False)
    escalated = [r for r in recs if r.escalated]
    assert escalated, "high-drift half must produce escalations"
    for r in escalated:
        assert r.human_decision in ("approve", "reject")
        assert r.human_rationale
        assert r.decision == "escalated"


def test_run_style_is_deterministic_with_mocks():
    a = run_style("linear_ramp", 12, MockOptimizer(), MockHuman(), verbose=False)
    b = run_style("linear_ramp", 12, MockOptimizer(), MockHuman(), verbose=False)
    assert [r.decision for r in a] == [r.decision for r in b]


# --- the LLM agents driven by a fake client ---------------------------------

def _fake_response(tool_name, tool_input):
    block = types.SimpleNamespace(type="tool_use", name=tool_name, input=tool_input)
    usage = types.SimpleNamespace(input_tokens=10, output_tokens=5)
    return types.SimpleNamespace(content=[block], usage=usage)


class _FakeMessages:
    def __init__(self, tool_name, tool_input):
        self._tool_name, self._tool_input = tool_name, tool_input
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _fake_response(self._tool_name, self._tool_input)


class _FakeClient:
    def __init__(self, tool_name, tool_input):
        self.messages = _FakeMessages(tool_name, tool_input)


def test_haiku_optimizer_parses_candidate_and_reasoning():
    client = _FakeClient("propose_change", {
        "type": "guc", "params": {"name": "shared_buffers", "value": "4GB"},
        "reversible": True, "reasoning": "raise buffers",
    })
    agent = HaikuOptimizerAgent(client=client)
    cand, meta = agent.propose(regime_context(0.7), [])
    assert isinstance(cand, Candidate) and cand.type == "guc"
    assert cand.params["name"] == "shared_buffers"
    assert meta["reasoning"] == "raise buffers"
    assert meta["tokens"]["input_tokens"] == 10
    # forced tool choice was used
    assert client.messages.calls[0]["tool_choice"]["name"] == "propose_change"


def test_optimizer_normalizes_nested_params():
    # Haiku sometimes nests params under the type name; the pore reads flat keys, so
    # a nested systemic GUC must be un-nested or it would silently fail to escalate.
    client = _FakeClient("propose_change", {
        "type": "guc", "params": {"guc": {"name": "shared_buffers", "value": "8GB"}},
        "reversible": True, "reasoning": "x",
    })
    cand, _ = HaikuOptimizerAgent(client=client).propose(regime_context(0.7), [])
    assert cand.params == {"name": "shared_buffers", "value": "8GB"}
    # and this flattened candidate is what makes the frozen pore escalate it
    from cleanroom import pore
    assert pore.evaluate(cand).requires_human_judgment is True


def test_sonnet_human_parses_decision():
    client = _FakeClient("render_judgment", {"decision": "reject", "rationale": "too risky"})
    agent = SonnetHumanAgent(client=client)
    from cleanroom.types import PoreResult
    pr = PoreResult(pore="reversibility", risk_level="high", requires_human_judgment=True, decision="escalate")
    decision, rationale, meta = agent.adjudicate(
        Candidate("migration", {"op": "drop"}, False), pr, regime_context(0.95))
    assert decision == "reject" and rationale == "too risky"


def test_sonnet_human_defaults_unknown_decision_to_reject():
    client = _FakeClient("render_judgment", {"decision": "maybe", "rationale": "?"})
    agent = SonnetHumanAgent(client=client)
    from cleanroom.types import PoreResult
    pr = PoreResult(pore="blast_radius", risk_level="high", requires_human_judgment=True, decision="escalate")
    decision, _, _ = agent.adjudicate(Candidate("guc", {"name": "fsync"}, True), pr, regime_context(0.7))
    assert decision == "reject"  # conservative default


def test_backoff_retries_transient_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 rate limit")
        return "ok"

    assert _with_backoff(flaky, base=0.0, cap=0.0, sleep=lambda s: None) == "ok"
    assert calls["n"] == 3


def test_backoff_reraises_non_transient_immediately():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise ValueError("bad schema")

    with pytest.raises(ValueError, match="bad schema"):
        _with_backoff(boom, base=0.0, sleep=lambda s: None)
    assert calls["n"] == 1  # not retried
