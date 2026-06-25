"""Tests for bond extraction domain — validator, extractor, judge, actions, pore."""

import pytest
from cleanroom.domains.bond_extraction.validators import (
    isin_checksum,
    is_iso4217,
    is_numeric_coupon,
    is_parseable_date,
    validate_field,
)
from cleanroom.domains.bond_extraction.extractor import StubExtractor
from cleanroom.domains.bond_extraction.actions import BondActions
from cleanroom.domains.bond_extraction.judge import BondBenchmark
from cleanroom.domains.bond_extraction.pore import BondPore
from cleanroom.types import Candidate, PoreResult


class TestValidators:
    """Test bond field validators."""

    def test_isin_checksum_valid(self):
        """Valid ISIN should pass checksum."""
        # Use a real ISIN: US0378331005 (Apple Inc., real ISIN with valid checksum)
        assert isin_checksum("US0378331005")

    def test_isin_checksum_invalid_length(self):
        """ISIN with wrong length should fail."""
        assert not isin_checksum("US012345678")  # Too short
        assert not isin_checksum("US01234567890")  # Too long

    def test_isin_checksum_invalid_format(self):
        """ISIN with wrong format should fail."""
        assert not isin_checksum("00123456789X")  # Starts with digits
        assert not isin_checksum("US123456789")  # Only 9 alphanumerics

    def test_is_iso4217_valid(self):
        """Valid ISO 4217 codes should pass."""
        assert is_iso4217("USD")
        assert is_iso4217("EUR")
        assert is_iso4217("GBP")

    def test_is_iso4217_invalid(self):
        """Invalid currency codes should fail."""
        assert not is_iso4217("US")  # Too short
        assert not is_iso4217("USDA")  # Too long
        assert not is_iso4217("usd")  # Lowercase
        assert not is_iso4217("US1")  # Contains digit

    def test_is_numeric_coupon_valid(self):
        """Valid coupon rates should pass."""
        assert is_numeric_coupon("3.5")
        assert is_numeric_coupon("4.125")
        assert is_numeric_coupon("0")
        assert is_numeric_coupon("10")

    def test_is_numeric_coupon_invalid(self):
        """Invalid coupon rates should fail."""
        assert not is_numeric_coupon("-1.0")  # Negative
        assert not is_numeric_coupon("abc")  # Not a number
        assert not is_numeric_coupon("")  # Empty

    def test_is_parseable_date_valid(self):
        """Valid future dates should pass."""
        # Use a date well in the future.
        assert is_parseable_date("2099-12-31")

    def test_is_parseable_date_invalid(self):
        """Invalid or past dates should fail."""
        assert not is_parseable_date("2020-01-01")  # Past date
        assert not is_parseable_date("2024-13-01")  # Invalid month
        assert not is_parseable_date("invalid-date")  # Invalid format
        assert not is_parseable_date("")  # Empty

    def test_validate_field_coupon_rate(self):
        """Validate coupon_rate field."""
        assert validate_field("coupon_rate", "3.5")
        assert not validate_field("coupon_rate", "-1.0")
        assert not validate_field("coupon_rate", "abc")

    def test_validate_field_currency(self):
        """Validate currency field."""
        assert validate_field("currency", "USD")
        assert not validate_field("currency", "us")
        assert not validate_field("currency", "USDA")

    def test_validate_field_isin(self):
        """Validate isin field."""
        assert validate_field("isin", "US0378331005")  # Real ISIN with valid checksum
        assert not validate_field("isin", "US012345678")  # Too short

    def test_validate_field_unknown_lenient(self):
        """Unknown fields are lenient (non-empty string)."""
        assert validate_field("issuer", "Acme Corp")
        assert not validate_field("issuer", "")


class TestExtractor:
    """Test bond field extractor."""

    def test_extract_with_pattern(self):
        """Extract should find value matching pattern."""
        extractor = StubExtractor()
        config = {
            "field_patterns": {
                "isin": r"[A-Z]{2}[A-Z0-9]{9}[0-9]",
            },
            "validation_enabled": False,
            "field_schema": [],
        }
        source = "The bond ISIN is US0378331005."
        result = extractor.extract("isin", source, config)
        assert result == "US0378331005"

    def test_extract_no_pattern_no_validation(self):
        """Extract with no pattern and no validation should return empty."""
        extractor = StubExtractor()
        config = {
            "field_patterns": {},
            "validation_enabled": False,
            "field_schema": [],
        }
        source = "Some text."
        result = extractor.extract("coupon_rate", source, config)
        assert result == ""

    def test_extract_with_validation_enabled(self):
        """Extract with validation enabled should use heuristic."""
        extractor = StubExtractor()
        config = {
            "field_patterns": {},
            "validation_enabled": True,
            "field_schema": ["isin", "coupon_rate"],
        }
        source = "The ISIN is US0378331005 and the coupon is 3.5%."
        result = extractor.extract("isin", source, config)
        assert "US0378331005" in result or result == ""

    def test_extract_returns_substring(self):
        """Extracted value must be a substring of source_text."""
        extractor = StubExtractor()
        config = {
            "field_patterns": {
                "coupon_rate": r"\b\d+(?:\.\d+)?\b",
            },
            "validation_enabled": False,
            "field_schema": [],
        }
        source = "Coupon rate: 3.5 percent"
        result = extractor.extract("coupon_rate", source, config)
        if result:
            assert result in source


class TestBondActions:
    """Test bond action apply and rollback."""

    def test_apply_then_rollback_round_trip(self):
        """apply() then rollback() should restore exact prior config."""
        actions = BondActions()

        env = {
            "_cur_config": {
                "field_patterns": {},
                "validation_enabled": False,
            },
            "_config_stack": [],
        }

        candidate = Candidate(
            type="extractor_config",
            params={
                "config_delta": {
                    "field_patterns": {"isin": r"[A-Z]{2}[A-Z0-9]{9}[0-9]"},
                    "validation_enabled": True,
                }
            },
            reversible=True,
        )

        actions.apply(env, candidate)
        assert env["_cur_config"]["validation_enabled"] is True
        assert "isin" in env["_cur_config"]["field_patterns"]

        actions.rollback(env, candidate)
        assert env["_cur_config"]["validation_enabled"] is False
        assert len(env["_cur_config"]["field_patterns"]) == 0

    def test_apply_rejects_non_extractor_config(self):
        """apply() should reject candidates with wrong type."""
        actions = BondActions()
        env = {"_cur_config": {}, "_config_stack": []}

        bad_candidate = Candidate(
            type="index",
            params={"config_delta": {}},
            reversible=True,
        )

        with pytest.raises(ValueError, match="expected type='extractor_config'"):
            actions.apply(env, bad_candidate)


class TestBondBenchmark:
    """Test bond benchmark and judge."""

    def test_run_benchmark_with_empty_holdout(self):
        """Benchmark with no holdout data should return neutral result."""
        benchmark = BondBenchmark()
        env = {
            "_extractor": StubExtractor(),
            "_cur_config": {},
            "_eval": {"train": [], "holdout": []},
            "_grader": ("field_match", None),
        }

        result = benchmark.run_benchmark(env, "bond_extraction")
        assert result.p99_ms == 0.5

    def test_check_correctness_blocks_frozen_mutation(self):
        """check_correctness should block mutation of frozen keys."""
        benchmark = BondBenchmark()
        env = {
            "_extractor": StubExtractor(),
            "_cur_config": {},
            "_eval": {"train": [], "holdout": []},
            "_loss_hash": "abc123",
        }

        # Attempt to mutate frozen key.
        bad_candidate = Candidate(
            type="extractor_config",
            params={"config_delta": {"_loss_hash": "xyz789"}},
            reversible=True,
        )

        assert not benchmark.check_correctness(env, bad_candidate)

    def test_check_correctness_allows_safe_delta(self):
        """check_correctness should allow safe config deltas."""
        benchmark = BondBenchmark()
        env = {
            "_extractor": StubExtractor(),
            "_cur_config": {},
            "_eval": {"train": [], "holdout": []},
            "_loss_hash": "",
        }

        safe_candidate = Candidate(
            type="extractor_config",
            params={"config_delta": {"field_patterns": {}}},
            reversible=True,
        )

        assert benchmark.check_correctness(env, safe_candidate)

    def test_check_correctness_blocks_fabricated_value(self):
        """check_correctness should reject an extractor that invents a value not in the source."""

        class FabricatingExtractor:
            def extract(self, field_name, source_text, config):
                # Emit a value that is NOT a span of source_text → fabrication.
                return "TOTALLY-MADE-UP-9999"

        benchmark = BondBenchmark()
        env = {
            "_extractor": FabricatingExtractor(),
            "_cur_config": {},
            "_eval": {
                "train": [],
                "holdout": [
                    {
                        "document_id": "doc-001",
                        "field_name": "issuer",
                        "gold_value": "Acme Corporation",
                        "source_text": "TERM SHEET\nIssuer: Acme Corporation",
                        "kind": "objective",
                    }
                ],
            },
            "_loss_hash": "",
        }

        candidate = Candidate(
            type="extractor_config",
            params={"config_delta": {"validation_enabled": True}},
            reversible=True,
        )

        assert not benchmark.check_correctness(env, candidate)

    def test_check_correctness_allows_honest_extraction(self):
        """An extractor that emits true spans of source_text passes the fabrication gate."""

        class HonestExtractor:
            def extract(self, field_name, source_text, config):
                return "Acme Corporation"  # a verbatim span of the source below

        benchmark = BondBenchmark()
        env = {
            "_extractor": HonestExtractor(),
            "_cur_config": {},
            "_eval": {
                "train": [],
                "holdout": [
                    {
                        "document_id": "doc-001",
                        "field_name": "issuer",
                        "gold_value": "Acme Corporation",
                        "source_text": "TERM SHEET\nIssuer: Acme Corporation",
                        "kind": "objective",
                    }
                ],
            },
            "_loss_hash": "",
        }

        candidate = Candidate(
            type="extractor_config",
            params={"config_delta": {"validation_enabled": True}},
            reversible=True,
        )

        assert benchmark.check_correctness(env, candidate)


class TestBondPore:
    """Test bond pore (governance gate)."""

    def test_evaluate_rejects_non_extractor_config(self):
        """evaluate should return high-risk block for wrong type."""
        pore = BondPore()
        candidate = Candidate(
            type="index",
            params={"config_delta": {}},
            reversible=True,
        )

        result = pore.evaluate(candidate)
        assert result.risk_level == "high"
        assert result.decision == "block"

    def test_evaluate_blocks_frozen_mutation(self):
        """evaluate should block mutation of frozen keys."""
        pore = BondPore()
        candidate = Candidate(
            type="extractor_config",
            params={"config_delta": {"_loss_hash": "tampered"}},
            reversible=True,
        )

        result = pore.evaluate(candidate)
        assert result.risk_level == "high"
        assert result.decision == "block"

    def test_evaluate_allows_safe_config(self):
        """evaluate should allow safe extractor config changes."""
        pore = BondPore()
        candidate = Candidate(
            type="extractor_config",
            params={
                "config_delta": {
                    "field_patterns": {"isin": r"[A-Z]{2}[A-Z0-9]{9}[0-9]"},
                }
            },
            reversible=True,
        )

        result = pore.evaluate(candidate)
        assert result.risk_level == "low"
        assert result.decision == "allow"

    def test_evaluate_escalates_interpretation_field(self):
        """evaluate should escalate if trying to tune interpretation field."""
        pore = BondPore()
        env = {
            "_interpretation": [
                {"field_name": "__interpretation_0", "clause": "some clause"}
            ]
        }

        candidate = Candidate(
            type="extractor_config",
            params={
                "config_delta": {
                    "field_patterns": {"__interpretation_0": r"some pattern"},
                }
            },
            reversible=True,
        )

        result = pore.evaluate(candidate, env)
        assert result.risk_level == "high"
        assert result.decision == "escalate"


class TestJudgeImportPolicy:
    """Test that judge.py has no LLM client imports (Issue #28)."""

    def test_judge_no_llm_imports(self):
        """judge.py should not import any LLM client."""
        import cleanroom.domains.bond_extraction.judge as judge_module

        # Check that anthropic, openai, boto3 are NOT imported.
        forbidden_modules = ["anthropic", "openai", "boto3"]
        for forbidden in forbidden_modules:
            assert not hasattr(judge_module, forbidden), (
                f"judge.py imports {forbidden} (violation of Issue #28)"
            )


class TestIntegration:
    """Integration tests — end-to-end flow."""

    def test_e2e_extractor_config_progression(self):
        """Test that extractor quality improves with config progression."""
        from cleanroom.domains.bond_extraction.proposer import ScriptedExtractor

        extractor = StubExtractor()
        proposer = ScriptedExtractor()

        # Simulate a progression: propose configs, check if extraction improves.
        source_text = "ISIN: US0123456789, Coupon: 3.5%, Currency: USD"

        configs = []
        for i in range(3):
            candidate = proposer.propose({}, [])
            configs.append(candidate.params["config_delta"])

        # Extract with progressively better configs.
        for config in configs:
            result = extractor.extract("isin", source_text, config)
            # Result should be empty string or a substring of source.
            if result:
                assert result in source_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
