"""Tests for the manifesto drift sweep — the two boundary readings.

Offline (CannedBenchmark + InMemoryLogClient, no DB). Asserts the *properties* the
manifesto claims, produced by the real frozen pore via the interior loop:
  - spatial: escalation rate rises (monotone) with workload drift;
  - longitudinal: at a fixed drift, the per-window escalation ratio stays flat.
"""

from cleanroom.fixtures import InMemoryLogClient
from scripts.run_drift_sweep import run_ramp, run_stationary, _severity


def test_severity_sequence_is_deterministic_and_in_range():
    vals = [_severity(i) for i in range(50)]
    assert all(0.0 <= v < 1.0 for v in vals)
    assert vals == [_severity(i) for i in range(50)]  # deterministic, no randomness


def test_spatial_escalation_rate_rises_with_drift():
    spatial = run_ramp(InMemoryLogClient(), [0.0, 0.5, 1.0], iterations=12)
    rate = {round(r["drift_level"], 3): r["escalation_rate"] for r in spatial}
    assert rate[0.0] == 0.0
    assert rate[0.0] < rate[0.5] < rate[1.0]  # monotone rising — the spatial reading
    assert rate[1.0] >= 0.9


def test_longitudinal_flat_at_fixed_drift():
    long = run_stationary(InMemoryLogClient(), drift=0.4, iterations=61)
    ratios = [r["ratio"] for r in long]
    assert len(ratios) >= 4
    # Flat by design: windows stay in a tight band around the (fixed) drift level.
    assert max(ratios) - min(ratios) <= 0.35
    assert 0.25 <= sum(ratios) / len(ratios) <= 0.55  # mean ≈ drift 0.4


def test_escalations_are_pore_decisions_not_set_by_hand():
    """The loop+frozen pore must produce the 'escalated' decisions; high drift -> some."""
    lc = InMemoryLogClient()
    run_ramp(lc, [1.0], iterations=12)
    decisions = {e["decision"] for e in lc.read_experiments()}
    assert "escalated" in decisions
