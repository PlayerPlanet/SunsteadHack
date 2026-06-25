"""Loss specification and freezing for BYO-Agent vertical.

The loss spec defines the grader + eval dataset + action space + constraints.
It is frozen (content-hashed) before iteration 0, preventing the optimizer from
gaming the metric. The frozen hash is checked on every iteration to detect tampering.
"""

import hashlib
import json

from cleanroom.types import Candidate


def hash_grader_dataset(grader: tuple, dataset: dict) -> str:
    """Compute SHA256 hash of (grader, dataset) for tamper detection.

    Args:
        grader: (kind, callable) tuple.
        dataset: Dict with 'train' and 'holdout' lists.

    Returns:
        Hex SHA256 string.
    """
    grader_kind, _ = grader
    hash_input = json.dumps(
        {"grader_kind": grader_kind, "eval": dataset}, sort_keys=True
    )
    return hashlib.sha256(hash_input.encode()).hexdigest()


def build_loss_spec(
    objective: str,
    grader: tuple,
    dataset: dict,
    action_space: list,
    gameability_review: list = None,
) -> dict:
    """Build a loss specification dict matching the domain-onboarding straw-man.

    Args:
        objective: Task objective (e.g., "maximize accuracy on arithmetic problems").
        grader: (kind, callable) tuple where kind is "exact"|"regex"|"programmatic".
        dataset: Dict with 'train' and 'holdout' lists of {input, expected}.
        action_space: List of allowed action types (e.g., ["agent_config"]).
        gameability_review: Optional list of review comments.

    Returns:
        Dict with domain, version, objective, measurement, constraints,
        action_space, gameability_review, signed_by, content_hash.

    Raises:
        ValueError: If grader kind is not allowed.
    """
    grader_kind, _ = grader

    allowed_kinds = {"exact", "regex", "programmatic"}
    if grader_kind not in allowed_kinds:
        raise ValueError(
            f"Unsupported grader kind '{grader_kind}'. Allowed: {allowed_kinds}. "
            "LLM-as-judge is NOT allowed per Issue #28 (benchmark paradox)."
        )

    content_hash = hash_grader_dataset(grader, dataset)

    spec = {
        "domain": "byo_agent",
        "version": "1.0",
        "objective": objective,
        "measurement": "error_rate (1 - accuracy) on held-out split, lower=better",
        "constraints": {
            "max_iterations": 15,
            "action_space": action_space,
            "max_token_cost": 100000,  # rough estimate
        },
        "action_space": action_space,
        "gameability_review": gameability_review or [
            "Grader is deterministic (no LLM paradox)",
            "Eval split is held-out (never seen by proposer)",
            "Loss is frozen by content hash (no tampering)",
        ],
        "signed_by": "sunsteadhack-byo-agent-v1",
        "content_hash": content_hash,
    }

    return spec


def freeze_loss(logclient, task_id: str, loss_spec: dict) -> None:
    """Freeze the loss spec by writing a loss-definition experiment record.

    CRITICAL FOR ISSUE #28: Before iteration 0, write an immutable audit record
    of the grader + eval + constraints + content_hash. This is the SOURCE OF TRUTH
    for the frozen loss — the live env hash is verified against this record on
    every iteration to detect tampering.

    The "loss-definition" experiment (iteration -1, before the loop starts) is the
    commitment: the optimizer cannot change the grader, eval split, or constraints
    without creating a NEW loss-definition experiment (a new run/branch).

    Args:
        logclient: LogClient instance (InMemoryLogClient or real logclient).
        task_id: Task identifier.
        loss_spec: Loss specification dict (includes content_hash).

    Returns:
        int: The experiment_id of the loss-definition record (for audit trail).
    """
    # Write a synthetic "loss-definition" experiment record (iteration -1, pre-loop).
    # This creates an immutable record in the logclient so the loss spec is signed
    # and versioned before any optimization begins.
    exp_id = logclient.write_experiment(
        task_id=task_id,
        model="loss-definition",
        drift_level=0.0,
        candidate={"payload": loss_spec},
        baseline_p99=None,
        candidate_p99=None,
        cost_estimate=None,
        correctness_ok=True,  # Loss definition is always "correct" (it's a spec)
        within_noise=None,
        decision="freeze",  # Special decision marker: this is the loss freeze
    )
    # The loss_spec (including content_hash) is now permanently recorded in logclient.
    return exp_id
