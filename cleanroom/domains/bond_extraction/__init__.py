"""Bond extraction optimization vertical — extract corporate bond fields from term sheets.

The user brings a CSV dataset with gold labels (e.g., {document_id, field_name, gold_value}
and optionally interpretation clauses that require human review). This vertical runs the
auto-research loop to improve the extractor's config (field patterns, validation flags)
WITHOUT modifying the frozen grader/loss.

DESIGN PRINCIPLE (Issue #28 — the benchmark paradox):
The judge is the REFEREE. It imports NO LLM client. It grounds truth ONLY in:
  1. User-planted held-out labels (the answer key)
  2. Deterministic graders (field-level F1)

The extractor (the CONTESTANT) is measured only by its accuracy on the held-out
split. The proposer (agentic optimizer) receives ONLY the train split and can
NEVER see the holdout data or alter the grader/loss.
"""

import json
import os
from hashlib import sha256

from .actions import BondActions
from .extractor import StubExtractor
from .judge import BondBenchmark
from .pore import BondPore
from .proposer import BondProposer, ScriptedExtractor
from .validators import validate_field

__all__ = [
    "BondActions",
    "BondBenchmark",
    "BondPore",
    "BondProposer",
    "ScriptedExtractor",
    "StubExtractor",
    "validate_field",
    "build_env_from_task",
]


def build_env_from_task(task_dict: dict) -> dict:
    """Build a domain env dict from a bond extraction task specification.

    Args:
        task_dict: Dict with:
            - objective: str
            - eval_ref: path to JSONL file with {document_id, field_name, gold_value, split, kind, source_text}
            - grader: {"kind": "field_match"}
            - constraints: {"max_iterations": int}

    Returns:
        Domain env dict ready for run_loop:
          {
            "_cur_config": {field_patterns: {}, validation_enabled: False, field_schema: []},
            "_extractor": StubExtractor(),
            "_eval": {"train": [...], "holdout": [...]},
            "_grader": ("field_match", grader_fn),
            "_loss_hash": str,
            "_interpretation": [interpretation rows],
            "_logclient": None,
            "_config_stack": [],
          }

    Raises:
        ValueError: If task_dict is malformed or eval file not found.
    """
    objective = task_dict.get("objective", "(No objective)")
    # The control-plane dispatcher reconstructs the task dict from only the 7
    # TaskSpec fields, so eval_ref/grader arrive nested under `constraints`. Fall
    # back to top-level keys for callers (offline scripts/tests) that pass them flat.
    constraints = task_dict.get("constraints") or {}
    eval_ref = task_dict.get("eval_ref") or constraints.get("eval_ref", "")

    # Load eval dataset from JSONL file.
    eval_data = _load_eval_jsonl(eval_ref)
    if not eval_data:
        raise ValueError(f"Could not load eval data from {eval_ref}")

    # Split into train/holdout using the split field from the rows (already assigned by ingestion).
    train_holdout = _split_by_split_field(eval_data)

    # Separate interpretation rows (kind="interpretation") from the eval dict.
    interpretation_rows = [
        row for row in eval_data if row.get("kind") == "interpretation"
    ]

    # Build grader (field-match via F1).
    grader = ("field_match", BondBenchmark._compute_loss_hash)

    # Instantiate extractor.
    extractor = StubExtractor()

    # Build initial config (deterministic baseline: no patterns, no validation).
    initial_config = {
        "field_patterns": {},
        "validation_enabled": False,
        "field_schema": [],
    }

    # Build env dict.
    env = {
        "_cur_config": initial_config,
        "_extractor": extractor,
        "_eval": train_holdout,
        "_grader": grader,
        "_loss_hash": "",  # set below
        "_interpretation": interpretation_rows,
        "_logclient": None,
        "_config_stack": [],
    }

    # Freeze the loss using the SAME hash the judge recomputes in check_correctness.
    # If we hashed a different structure here, an untampered eval/grader would never
    # verify as unchanged — every candidate would be falsely flagged as tampering and
    # the honesty invariant would refuse to keep it, so the curve could never descend.
    env["_loss_hash"] = BondBenchmark._compute_loss_hash(env)

    return env


def _load_eval_jsonl(path: str) -> list[dict]:
    """Load eval data from a JSONL file.

    Each line is a JSON object with {document_id, field_name, gold_value, split, kind, source_text}.

    Args:
        path: Path to JSONL file (absolute or relative to CWD).

    Returns:
        List of dicts, or empty list if file not found.
    """
    if not os.path.exists(path):
        # Try relative to this package.
        package_dir = os.path.dirname(__file__)
        path = os.path.join(package_dir, path)

    if not os.path.exists(path):
        return []

    data = []
    try:
        with open(path, "r") as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
    except Exception:
        pass

    return data


def _split_by_split_field(data: list[dict]) -> dict:
    """Split eval data by the split field (already assigned by ingestion).

    Args:
        data: List of eval items with a "split" field.

    Returns:
        Dict with "train" and "holdout" keys.
    """
    train = [row for row in data if row.get("split") == "train"]
    holdout = [row for row in data if row.get("split") == "holdout"]
    return {"train": train, "holdout": holdout}


def _compute_loss_hash(train_holdout: dict) -> str:
    """Compute SHA256 hash of the eval structure (deterministic, reproducible).

    Args:
        train_holdout: Dict with "train" and "holdout" keys.

    Returns:
        SHA256 hex digest.
    """
    hash_input = json.dumps(train_holdout, sort_keys=True)
    return sha256(hash_input.encode()).hexdigest()
