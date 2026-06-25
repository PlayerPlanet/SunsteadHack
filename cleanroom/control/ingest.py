"""Bond extraction CSV ingestion — load CSV files and create task/dataset.

Converts CSV gold labels, optional splits, interpretation rows, and documents
into a structured task JSON and dataset JSONL ready for the loop.
"""

import csv
import hashlib
import json
import os
import re
import uuid
from io import StringIO

from cleanroom.domains.bond_extraction.validators import validate_field


def ingest_bond_csv(
    name: str,
    objective: str,
    gold_csv: str,
    splits_csv: str | None = None,
    interpretation_csv: str | None = None,
    documents_csv: str | None = None,
    tasks_dir: str | None = None,
    datasets_dir: str | None = None,
) -> dict:
    """Ingest bond CSV files and create task/dataset.

    Args:
        name: Human-readable task name.
        objective: Optimization objective description.
        gold_csv: Raw CSV file contents with columns {document_id, field_name, gold_value}.
        splits_csv: Optional raw CSV with {document_id, split} where split ∈ {train, holdout, test}.
        interpretation_csv: Optional raw CSV with {document_id, clause_or_question}.
        documents_csv: Optional raw CSV with {document_id, text}.

    Returns:
        Dict with:
          - task_id: Unique task identifier
          - dataset_path: Path to written dataset JSONL
          - n_documents: Number of unique documents
          - n_fields: Number of unique fields
          - n_holdout: Number of holdout rows
          - n_interpretation: Number of interpretation rows
          - warnings: List of validation warnings

    Raises:
        ValueError: If required columns are missing or gold set is empty.
        HTTPException: Mapped to 400 by the endpoint.
    """
    warnings = []

    # Parse gold CSV.
    gold_rows = _parse_csv(gold_csv, required_cols={"document_id", "field_name", "gold_value"})
    if not gold_rows:
        raise ValueError("gold_csv is empty or missing required columns (document_id, field_name, gold_value)")

    # Validate gold values; collect warnings for format violations.
    validated_gold = []
    for row in gold_rows:
        field_name = row["field_name"]
        gold_value = row["gold_value"]
        if not validate_field(field_name, gold_value):
            warnings.append(
                f"Row (doc={row.get('document_id')}, field={field_name}): "
                f"value '{gold_value}' fails format validation for field type"
            )
        else:
            validated_gold.append(row)

    if not validated_gold:
        raise ValueError("No gold rows survived validation (all failed format checks)")

    # Parse splits CSV (optional).
    if splits_csv:
        splits_rows = _parse_csv(splits_csv, required_cols={"document_id", "split"})
        splits_dict = {
            row["document_id"]: "holdout" if row["split"] == "test" else row["split"]
            for row in splits_rows
        }
    else:
        # Auto-split BY DOCUMENT (70% train, 30% holdout).
        splits_dict = _auto_split_by_document(validated_gold, train_frac=0.7)

    # Parse interpretation CSV (optional).
    interpretation_rows = []
    if interpretation_csv:
        interpretation_rows = _parse_csv(interpretation_csv, required_cols={"document_id", "clause_or_question"})

    # Parse documents CSV (optional).
    documents_dict = {}
    if documents_csv:
        doc_rows = _parse_csv(documents_csv, required_cols={"document_id", "text"})
        documents_dict = {row["document_id"]: row["text"] for row in doc_rows}

    # Synthesize term sheet texts for documents without provided text.
    all_doc_ids = set(row["document_id"] for row in validated_gold)
    for doc_id in all_doc_ids:
        if doc_id not in documents_dict:
            # Synthesize: gather all gold values for this document.
            doc_fields = [row for row in validated_gold if row["document_id"] == doc_id]
            documents_dict[doc_id] = _synthesize_term_sheet(doc_fields)

    # Build dataset JSONL: one line per (document_id, field_name) pair.
    dataset_rows = []
    for row in validated_gold:
        doc_id = row["document_id"]
        field_name = row["field_name"]
        gold_value = row["gold_value"]
        split = splits_dict.get(doc_id, "train")
        source_text = documents_dict.get(doc_id, "")

        dataset_rows.append({
            "document_id": doc_id,
            "field_name": field_name,
            "gold_value": gold_value,
            "split": split,
            "kind": "objective",
            "source_text": source_text,
        })

    # Add interpretation rows.
    n_interpretation = 0
    for row in interpretation_rows:
        doc_id = row["document_id"]
        clause = row["clause_or_question"]
        split = splits_dict.get(doc_id, "train")
        source_text = documents_dict.get(doc_id, "")

        dataset_rows.append({
            "document_id": doc_id,
            "field_name": f"__interpretation_{n_interpretation}",
            "gold_value": "",  # No gold value for interpretation rows.
            "split": split,
            "kind": "interpretation",
            "source_text": source_text,
            "clause": clause,
        })
        n_interpretation += 1

    # Count holdout objective rows.
    n_holdout = sum(
        1 for row in dataset_rows
        if row["split"] == "holdout" and row["kind"] == "objective"
    )

    # Generate task_id (slugified name + short uniqueness suffix).
    task_id = _generate_task_id(name)

    # Write dataset JSONL. Default to the bond_extraction package's datasets dir;
    # tests pass an explicit datasets_dir (e.g. tmp_path) to avoid polluting it.
    if datasets_dir is None:
        import cleanroom.domains.bond_extraction
        module_dir = os.path.dirname(cleanroom.domains.bond_extraction.__file__)
        datasets_dir = os.path.join(module_dir, "datasets")
    os.makedirs(datasets_dir, exist_ok=True)
    dataset_path = os.path.join(datasets_dir, f"{task_id}.jsonl")

    with open(dataset_path, "w") as f:
        for row in dataset_rows:
            f.write(json.dumps(row) + "\n")

    # Build task JSON.
    objective_fields = list(set(
        row["field_name"] for row in dataset_rows if row["kind"] == "objective"
    ))
    interpretation_fields = list(set(
        row["field_name"] for row in dataset_rows if row["kind"] == "interpretation"
    ))

    # A bond task is a valid 7-field TaskSpec so the control-plane registry can load
    # and dispatch it like any kernel/quant/bio task. The domain-specific data
    # (eval_ref + grader) lives under `constraints` — the one dict the dispatcher
    # carries through to build_env_from_task — because dispatch reconstructs the
    # task dict from only the 7 TaskSpec fields (see Operator.dispatch_run).
    task_json = {
        "task_id": task_id,
        "objective": objective,
        "workload_id": "bond_extraction",
        "action_space": ["extractor"],
        "db_ref": "(bond term-sheet dataset)",
        "constraints": {
            "max_iterations": 10,
            "eval_ref": dataset_path,
            "grader": {
                "kind": "field_match",
                "objective_fields": objective_fields,
                "interpretation_fields": interpretation_fields,
            },
        },
        "default_model": "scripted",
        "state": "active",
    }

    # Write task JSON. Default to the control package's tasks dir; tests pass an
    # explicit tasks_dir (e.g. tmp_path) to avoid polluting the shared registry dir.
    if tasks_dir is None:
        import cleanroom.control
        module_dir = os.path.dirname(cleanroom.control.__file__)
        tasks_dir = os.path.join(module_dir, "tasks")
    os.makedirs(tasks_dir, exist_ok=True)
    task_path = os.path.join(tasks_dir, f"{task_id}.json")

    with open(task_path, "w") as f:
        json.dump(task_json, f, indent=2)

    # Build response.
    return {
        "task_id": task_id,
        "dataset_path": dataset_path,
        "n_documents": len(all_doc_ids),
        "n_fields": len(objective_fields),
        "n_holdout": n_holdout,
        "n_interpretation": n_interpretation,
        "warnings": warnings,
    }


def _parse_csv(csv_contents: str, required_cols: set) -> list[dict]:
    """Parse CSV string into list of dicts.

    Args:
        csv_contents: Raw CSV file contents as string.
        required_cols: Set of required column names.

    Returns:
        List of dicts, one per row. Empty list if parsing fails or columns missing.

    Raises:
        ValueError: If required columns are missing.
    """
    try:
        reader = csv.DictReader(StringIO(csv_contents))
        rows = list(reader)
        if not rows:
            return []
        # Check for required columns.
        fieldnames = set(reader.fieldnames or [])
        if not required_cols.issubset(fieldnames):
            missing = required_cols - fieldnames
            raise ValueError(f"Missing required columns: {missing}")
        return rows
    except Exception as e:
        raise ValueError(f"Failed to parse CSV: {e}")


def _auto_split_by_document(
    gold_rows: list[dict], train_frac: float = 0.7
) -> dict:
    """Auto-split gold rows BY DOCUMENT into train/holdout.

    CRITICAL: All rows of a document share ONE split — never split a document
    across train/holdout (leakage guarantee).

    Args:
        gold_rows: List of gold rows with "document_id".
        train_frac: Fraction of documents for training (default 0.7).

    Returns:
        Dict mapping document_id -> split (train or holdout).
    """
    doc_ids = sorted(set(row["document_id"] for row in gold_rows))
    n_train = max(1, int(len(doc_ids) * train_frac))

    splits_dict = {}
    for i, doc_id in enumerate(doc_ids):
        splits_dict[doc_id] = "train" if i < n_train else "holdout"
    return splits_dict


def _synthesize_term_sheet(doc_fields: list[dict]) -> str:
    """Synthesize a deterministic term sheet text from gold field values.

    Ensures gold values appear verbatim in the text so the extractor
    can extract them (and pass the no-fabrication check).

    Args:
        doc_fields: List of {field_name, gold_value} dicts for one document.

    Returns:
        Synthetic term sheet text.
    """
    lines = ["CORPORATE BOND TERM SHEET"]
    for row in doc_fields:
        field_name = row.get("field_name", "")
        gold_value = row.get("gold_value", "")
        if field_name and gold_value:
            # Format as "Field Name: gold_value" so the extractor can find it.
            label = field_name.replace("_", " ").title()
            lines.append(f"{label}: {gold_value}")
    return "\n".join(lines)


def _generate_task_id(name: str) -> str:
    """Generate a filesystem-safe, unique task_id from a name.

    Slugifies the name and adds a short hash suffix for uniqueness.

    Args:
        name: Human-readable task name.

    Returns:
        Slugified task_id.
    """
    # Slugify: lowercase, replace spaces/special chars with hyphens.
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    # Add short hash for uniqueness.
    hash_suffix = hashlib.md5(name.encode()).hexdigest()[:6]
    return f"{slug}-{hash_suffix}"
