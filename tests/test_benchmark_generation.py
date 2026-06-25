"""Tests for the benchmark GENERATOR — the load-bearing, non-agentic ruler (issue #28).

If these pass, the benchmark is non-circular by construction: ground truth comes from
deterministic re-derivation (the clean pool the frozen judge passes) and planted truth
(errors we injected). No agent decides where the ambiguity is. These tests assert the
three invariants that make that true, plus reproducibility and the agent-loading contract.

Run: PYTHONPATH=. python -m pytest tests/test_benchmark_generation.py -q
"""

from bonds_instrument import judge
from bonds_instrument.claims import CATCHABLE, build_clean_claims, poison
from bonds_instrument.runner import generation_stats, load_agent, run_benchmark


def _build(seed=7):
    clean = build_clean_claims()
    return clean, poison(clean, seed=seed)


def test_clean_pool_all_pass_the_frozen_judge():
    """The clean pool is defined as 'the judge passes' — so it must, every one."""
    clean, _ = _build()
    assert clean, "no claims re-derived from materials"
    assert all(judge.passes(c.view) for c in clean)


def test_catchable_plants_actually_break_the_judge():
    """Every judge-CATCHABLE corruption must break the arithmetic — else the label lies."""
    _, stream = _build()
    catchable = [c for c in stream if c.corruption in CATCHABLE]
    assert catchable, "no catchable corruptions planted"
    assert all(not judge.passes(c.view) for c in catchable)


def test_unit_swap_evades_the_judge():
    """unit_swap leaves the arithmetic intact (only reasoning catches it). This split is
    the whole point: it's where the dumb judge MUST fall back to escalation, not clearing."""
    _, stream = _build()
    swaps = [c for c in stream if c.corruption == "unit_swap"]
    assert swaps, "no unit_swap corruptions planted"
    assert all(judge.passes(c.view) for c in swaps)


def test_labels_are_consistent():
    """truth matches how the claim was built; the agent-visible view never leaks the label."""
    _, stream = _build()
    for c in stream:
        if c.corruption is None:
            assert c.truth == "clean"
        elif c.corruption == "unverifiable":
            assert c.truth == "needs_human"
        else:
            assert c.truth == "error"
        assert "truth" not in c.view and "corruption" not in c.view


def test_generation_is_reproducible():
    """Same seed -> same planted stream (so a scorecard is reproducible)."""
    _, a = _build(seed=11)
    _, b = _build(seed=11)
    sig = lambda s: [(c.claim_id, c.truth, c.corruption) for c in s]
    assert sig(a) == sig(b)


def test_generation_stats_invariants_hold():
    """The runtime self-check the runner logs must report all-clean on real materials."""
    clean, stream = _build()
    g = generation_stats(clean, stream)
    assert g["clean_pass_judge"] == g["clean_pool"]
    assert g["catchable_break_judge"][0] == g["catchable_break_judge"][1]
    assert g["uncatchable_evade_judge"][0] == g["uncatchable_evade_judge"][1]


def test_load_agent_contract():
    """The BYO-agent loader resolves module:Attr and enforces the review() contract."""
    agent = load_agent("bonds_instrument.candidates:DQAgentCandidate", use_llm=False)
    assert hasattr(agent, "review") and agent.name
    try:
        load_agent("bonds_instrument.candidates:NoSuchThing")
    except AttributeError:
        pass
    else:
        raise AssertionError("expected AttributeError for a missing attr")


def test_end_to_end_scorecard_shape():
    """The take-home agent scores on the sample and returns a well-formed scorecard."""
    sc = run_benchmark("2026-06-23_100-bond-sample-takehome",
                       "bonds_instrument.candidates:DQAgentCandidate", use_llm=False)
    assert sc["agent"] == "dq_agent"
    assert sc["n_claims"] > 0
    assert 0.0 <= sc["overall"]["false_clear_rate"] <= 1.0
    assert sc["by_drift_bin"] and all("false_clear_rate" in b for b in sc["by_drift_bin"])
