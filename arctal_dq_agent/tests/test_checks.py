"""Unit tests for the deterministic (Tier-0) checks.

Synthetic rows only — no data files, no LLM. These pin the arithmetic identities
and, importantly, the *disposition* each break gets (auto_correct vs flag), since
that located-autonomy decision is the heart of the agent.
"""

from agent.checks import (
    check_alloc_recon, check_category_count, check_coverage, check_date_sanity,
    check_fx_consensus, check_per_million, check_share_def,
)
from agent.data import Context, PeerStat


def test_per_million_clean_passes():
    row = {"isin": "X", "impact_metric": "m", "impact_value": "100",
           "impact_per_million_USD": "10", "bond_USD_amount": "10000000",  # 100/(10M/1e6)=10
           "source_trail": "denom=bond"}
    assert check_per_million(row, Context()) == []


def test_per_million_break_is_autocorrect_with_value():
    row = {"isin": "X", "impact_metric": "m", "impact_value": "100",
           "impact_per_million_USD": "99",  # should be 10
           "bond_USD_amount": "10000000", "source_trail": "denom=bond"}
    (f,) = check_per_million(row, Context())
    assert f.check_id == "per_million" and f.disposition == "auto_correct"
    assert f.proposed_correction == 10.0


def test_per_million_skips_allocation_denominated():
    # denom=allocation needs the allocation USD we don't hold here -> no claim.
    row = {"isin": "X", "impact_metric": "m", "impact_value": "100",
           "impact_per_million_USD": "99", "bond_USD_amount": "10000000",
           "source_trail": "denom=allocation"}
    assert check_per_million(row, Context()) == []


def test_coverage_autocorrect():
    row = {"isin": "X", "bond_USD_amount": "200", "total_USD_allocated": "100",
           "allocation_coverage_pct": "90"}  # true = 50
    (f,) = check_coverage(row, Context())
    assert f.disposition == "auto_correct" and f.proposed_correction == 50.0


def test_alloc_recon_flags_not_autocorrects():
    # Which of the three numbers is wrong is undetermined -> flag, no correction.
    row = {"isin": "X", "bond_USD_amount": "1000", "total_USD_allocated": "600",
           "total_USD_unallocated": "300"}  # 600+300 != 1000
    (f,) = check_alloc_recon(row, Context())
    assert f.disposition == "flag" and f.proposed_correction is None


def test_category_count_offby_one():
    row = {"isin": "X", "pre_icma_categories_number": "2",
           "pre_icma_categories": "A;B;C", "post_icma_categories_number": "1",
           "post_icma_categories": "A"}
    fs = check_category_count(row, Context())
    assert len(fs) == 1 and fs[0].proposed_correction == 3


def test_fx_consensus_uses_corpus_median():
    ctx = Context(fx_consensus={"EUR": 1.10})
    ok = {"isin": "X", "bond_amount": "100", "bond_USD_amount": "112", "bond_currency": "EUR"}
    bad = {"isin": "Y", "bond_amount": "100", "bond_USD_amount": "130", "bond_currency": "EUR"}
    assert check_fx_consensus(ok, ctx) == []          # 1.12 within 5% of 1.10
    (f,) = check_fx_consensus(bad, ctx)               # 1.30 is ~18% off
    assert f.check_id == "fx_consensus" and f.disposition == "flag"


def test_date_sanity():
    bad = {"isin": "X", "placement_date": "2030-01-01", "maturity_date": "2025-01-01"}
    good = {"isin": "X", "placement_date": "2020-01-01", "maturity_date": "2030-01-01"}
    assert check_date_sanity(good, Context()) == []
    assert check_date_sanity(bad, Context())[0].check_id == "date_sanity"


def test_share_def_autocorrect():
    row = {"isin": "X", "post_allocation_share_of_total": "0.5",
           "post_allocation_USD": "100", "bond_USD_amount": "1000",  # true 0.1
           "post_icma_category": "Renewable Energy"}
    (f,) = check_share_def(row, Context())
    assert f.disposition == "auto_correct" and f.proposed_correction == 0.1
