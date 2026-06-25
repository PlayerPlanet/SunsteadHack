"""Unit tests for source-trail re-derivation and the verdict collapse.

The trail check is the flagship "beyond SQL" surface, so these pin its two
behaviours that matter most: it catches a stored value that contradicts its own
narrated derivation, and it does NOT fire on mere display-rounding.
"""

from agent.data import Context
from agent.review import decide
from agent.trail import reconcile_impact_trail


def _impact(value, trail, **kw):
    row = {"isin": "X", "impact_metric": "Annual generation", "impact_value": str(value),
           "impact_unit": "MWh", "bond_USD_amount": "15344000000", "source_trail": trail}
    row.update(kw)
    return row


def test_catches_1000x_value_mismatch():
    # Real sample shape: trail derives 989,000 but the stored value is 989,000,000.
    trail = ("989,000.00 MWh (from source, denom=bond, entry=category); "
             "989,000.00 / 15,344.0M USD = 64.46 MWh/$M")
    fs = reconcile_impact_trail(_impact(989_000_000.0, trail))
    ids = {f.check_id for f in fs}
    assert "trail_value_mismatch" in ids
    f = next(f for f in fs if f.check_id == "trail_value_mismatch")
    assert f.severity == "high" and f.evidence["trail_derived_value"] == 989_000.0


def test_rounding_is_not_a_mismatch():
    # Stored 0.147 vs trail-displayed 0.15 is pure 2-dp rounding -> no finding.
    trail = "0.15 ha (from source, denom=bond, entry=category); 0.15 / 1,170.6M USD = 0.00 ha/$M"
    fs = reconcile_impact_trail(_impact(0.147, trail))
    assert [f for f in fs if f.check_id == "trail_value_mismatch"] == []


def test_bond_share_step_internal_consistency():
    # base × bond_share should equal the stated product; 53044*0.18 = 9547.92 (clean).
    clean = ("53,044.00 MWh (from source, entry=category) × bond_share 0.180000 "
             "= 9,547.92 MWh; 9,547.92 / 1,170.6M USD = 8.16 MWh/$M")
    assert reconcile_impact_trail(_impact(9547.92, clean, bond_USD_amount="1170600000")) == []
    # break the product so base×share no longer reconciles
    broken = ("53,044.00 MWh (from source, entry=category) × bond_share 0.180000 "
              "= 25,000.00 MWh; 25,000.00 / 1,170.6M USD = 21.36 MWh/$M")
    fs = reconcile_impact_trail(_impact(25000.0, broken, bond_USD_amount="1170600000"))
    assert any(f.check_id == "trail_share_inconsistent" for f in fs)


def test_clean_trail_no_findings():
    trail = ("989,000.00 MWh (from source, denom=bond, entry=category); "
             "989,000.00 / 15,344.0M USD = 64.46 MWh/$M")
    assert reconcile_impact_trail(_impact(989_000.0, trail)) == []


def test_decide_precedence_error_beats_escalate():
    fs = reconcile_impact_trail(_impact(
        989_000_000.0,
        "989,000.00 MWh (from source, denom=bond); 989,000.00 / 15,344.0M USD = 64.46 MWh/$M"))
    # a concrete arithmetic issue collapses to verdict "error"
    assert decide(fs).verdict == "error"
    # and an empty finding list stands behind the value
    assert decide([]).verdict == "ok"
