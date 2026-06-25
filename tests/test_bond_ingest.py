"""Tests for bond CSV ingestion — verify task/dataset file generation.

All ingestion writes are routed to a pytest tmp_path via the tasks_dir/datasets_dir
parameters so the suite never pollutes the shared cleanroom/control/tasks registry dir.
"""

import json
import os
import pytest
from cleanroom.control.ingest import ingest_bond_csv


def _ingest(tmp_path, **kwargs):
    """Run ingest_bond_csv with output redirected into the test's tmp_path."""
    return ingest_bond_csv(
        tasks_dir=str(tmp_path / "tasks"),
        datasets_dir=str(tmp_path / "datasets"),
        **kwargs,
    )


class TestIngestBondCSV:
    """Test bond CSV ingestion end-to-end."""

    def test_ingest_sample_gold_csv(self, tmp_path):
        """Ingest sample gold CSV and verify output."""
        gold_csv = """document_id,field_name,gold_value
doc-001,issuer,Acme Corporation
doc-001,isin,US0378331005
doc-001,coupon_rate,3.5
doc-002,issuer,Global Inc
doc-002,isin,IE00B4L5Y983
doc-002,coupon_rate,4.125
"""

        result = _ingest(
            tmp_path,
            name="test-task-1",
            objective="Extract bond fields from documents",
            gold_csv=gold_csv,
        )

        assert result["task_id"]
        assert "test-task-1" in result["task_id"].lower()
        assert result["n_documents"] == 2
        assert result["n_fields"] == 3
        assert result["n_holdout"] >= 0
        assert os.path.exists(result["dataset_path"])
        # Task JSON should exist in the (tmp) tasks directory.
        task_path = tmp_path / "tasks" / f"{result['task_id']}.json"
        assert task_path.exists()

    def test_ingest_with_splits_csv(self, tmp_path):
        """Ingest with explicit splits CSV."""
        gold_csv = """document_id,field_name,gold_value
doc-001,issuer,Acme
doc-001,isin,US0378331005
doc-002,issuer,Global
doc-002,isin,IE00B4L5Y983
"""

        splits_csv = """document_id,split
doc-001,train
doc-002,holdout
"""

        result = _ingest(
            tmp_path,
            name="test-task-2",
            objective="Test with explicit splits",
            gold_csv=gold_csv,
            splits_csv=splits_csv,
        )

        assert result["n_holdout"] == 2  # 2 holdout rows (1 per document)
        # Verify splits in JSONL.
        with open(result["dataset_path"]) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        holdout_rows = [r for r in rows if r["split"] == "holdout"]
        assert len(holdout_rows) >= 1

    def test_ingest_never_splits_document_rows(self, tmp_path):
        """Verify that all rows of a document share one split (no leakage)."""
        gold_csv = """document_id,field_name,gold_value
doc-001,issuer,Acme
doc-001,isin,US0378331005
doc-001,coupon_rate,3.5
doc-002,issuer,Global
doc-002,isin,IE00B4L5Y983
doc-002,coupon_rate,4.125
"""

        result = _ingest(
            tmp_path,
            name="test-task-3",
            objective="Verify no document split",
            gold_csv=gold_csv,
        )

        with open(result["dataset_path"]) as f:
            rows = [json.loads(line) for line in f if line.strip()]

        # Group by document_id and check all rows have same split.
        doc_splits = {}
        for row in rows:
            doc_id = row["document_id"]
            split = row["split"]
            if doc_id not in doc_splits:
                doc_splits[doc_id] = split
            else:
                assert doc_splits[doc_id] == split, (
                    f"Document {doc_id} has rows in different splits"
                )

    def test_ingest_with_interpretation_csv(self, tmp_path):
        """Ingest with interpretation (non-gold) rows."""
        gold_csv = """document_id,field_name,gold_value
doc-001,issuer,Acme
doc-001,isin,US0378331005
"""

        interpretation_csv = """document_id,clause_or_question
doc-001,Is this bond investment-grade?
doc-001,What is the credit rating?
"""

        result = _ingest(
            tmp_path,
            name="test-task-4",
            objective="Test with interpretations",
            gold_csv=gold_csv,
            interpretation_csv=interpretation_csv,
        )

        assert result["n_interpretation"] == 2
        # Verify interpretation rows in JSONL.
        with open(result["dataset_path"]) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        interpretation_rows = [r for r in rows if r["kind"] == "interpretation"]
        assert len(interpretation_rows) == 2

    def test_ingest_with_documents_csv(self, tmp_path):
        """Ingest with explicit document texts."""
        gold_csv = """document_id,field_name,gold_value
doc-001,issuer,Acme
doc-001,isin,US0378331005
"""

        documents_csv = """document_id,text
doc-001,This is the full term sheet for Acme bonds. ISIN: US0378331005.
"""

        result = _ingest(
            tmp_path,
            name="test-task-5",
            objective="Test with document texts",
            gold_csv=gold_csv,
            documents_csv=documents_csv,
        )

        with open(result["dataset_path"]) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        # Verify source_text is populated from documents_csv.
        assert rows[0]["source_text"] == "This is the full term sheet for Acme bonds. ISIN: US0378331005."

    def test_ingest_synthesizes_missing_documents(self, tmp_path):
        """Ingest should synthesize term sheet for documents without explicit text."""
        gold_csv = """document_id,field_name,gold_value
doc-001,issuer,Acme
doc-001,coupon_rate,3.5
"""

        result = _ingest(
            tmp_path,
            name="test-task-6",
            objective="Test document synthesis",
            gold_csv=gold_csv,
        )

        with open(result["dataset_path"]) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        # Verify source_text is synthesized.
        assert rows[0]["source_text"]
        assert "Acme" in rows[0]["source_text"] or "3.5" in rows[0]["source_text"]

    def test_ingest_rejects_missing_required_columns(self, tmp_path):
        """Ingest should raise ValueError for missing required columns."""
        bad_gold_csv = """document_id,field_name
doc-001,issuer
"""

        with pytest.raises(ValueError, match="Missing required columns"):
            _ingest(
                tmp_path,
                name="bad-task",
                objective="Bad gold CSV",
                gold_csv=bad_gold_csv,
            )

    def test_ingest_rejects_empty_gold_csv(self, tmp_path):
        """Ingest should raise ValueError for empty gold CSV."""
        with pytest.raises(ValueError, match="empty or missing"):
            _ingest(
                tmp_path,
                name="empty-task",
                objective="Empty gold",
                gold_csv="",
            )

    def test_ingest_warns_on_validation_failure(self, tmp_path):
        """Ingest should warn (not hard-fail) on validation failures."""
        gold_csv = """document_id,field_name,gold_value
doc-001,coupon_rate,3.5
doc-001,coupon_rate,-1.0
doc-001,currency,USDA
"""

        result = _ingest(
            tmp_path,
            name="test-task-7",
            objective="Test warnings",
            gold_csv=gold_csv,
        )

        assert len(result["warnings"]) > 0
        # The ingestion should succeed but with warnings.
        assert result["task_id"]

    def test_task_json_structure(self, tmp_path):
        """Verify task JSON is a valid 7-field TaskSpec with eval_ref/grader nested in constraints."""
        gold_csv = """document_id,field_name,gold_value
doc-001,issuer,Acme
doc-001,isin,US0378331005
doc-001,coupon_rate,3.5
doc-001,currency,USD
"""

        result = _ingest(
            tmp_path,
            name="test-task-8",
            objective="Test task JSON",
            gold_csv=gold_csv,
        )

        task_path = tmp_path / "tasks" / f"{result['task_id']}.json"
        with open(task_path) as f:
            task_json = json.load(f)

        assert task_json["task_id"] == result["task_id"]
        assert task_json["workload_id"] == "bond_extraction"
        assert task_json["objective"] == "Test task JSON"
        assert task_json["action_space"] == ["extractor"]
        assert task_json["default_model"] == "scripted"
        assert task_json["state"] == "active"
        # Domain data lives under constraints (the dict the dispatcher carries through).
        constraints = task_json["constraints"]
        assert constraints["max_iterations"] == 10
        assert constraints["eval_ref"].endswith(".jsonl")
        grader = constraints["grader"]
        assert grader["kind"] == "field_match"
        assert "objective_fields" in grader
        assert "interpretation_fields" in grader

    def test_task_json_loads_as_dispatchable_taskspec(self, tmp_path):
        """The produced task JSON must load through the registry (regression guard).

        The control-plane registry constructs TaskSpec(**data); a task JSON carrying
        non-TaskSpec keys at the top level would be silently skipped and become
        undispatchable. This asserts the ingested task is a clean 7-field spec.
        """
        from cleanroom.control.registry.store import TaskRegistryStore

        gold_csv = """document_id,field_name,gold_value
doc-001,issuer,Acme
doc-001,coupon_rate,3.5
doc-002,issuer,Global
doc-002,coupon_rate,4.0
"""
        result = _ingest(
            tmp_path,
            name="dispatchable-task",
            objective="Must be registry-loadable",
            gold_csv=gold_csv,
        )

        store = TaskRegistryStore(tmp_path / "tasks")
        spec = store.get(result["task_id"])
        assert spec is not None, "ingested bond task did not load as a TaskSpec"
        assert spec.workload_id == "bond_extraction"
        assert spec.constraints.get("eval_ref", "").endswith(".jsonl")

    def test_dataset_jsonl_structure(self, tmp_path):
        """Verify dataset JSONL has correct structure."""
        gold_csv = """document_id,field_name,gold_value
doc-001,issuer,Acme
doc-002,isin,US0378331005
"""

        result = _ingest(
            tmp_path,
            name="test-task-9",
            objective="Test dataset JSONL",
            gold_csv=gold_csv,
        )

        with open(result["dataset_path"]) as f:
            rows = [json.loads(line) for line in f if line.strip()]

        assert len(rows) >= 2
        for row in rows:
            assert "document_id" in row
            assert "field_name" in row
            assert "gold_value" in row
            assert "split" in row
            assert row["split"] in ["train", "holdout"]
            assert "kind" in row
            assert row["kind"] in ["objective", "interpretation"]
            assert "source_text" in row


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
