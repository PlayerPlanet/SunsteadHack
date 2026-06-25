"""BYO-Agent optimization vertical — user-supplied agent + user-supplied task.

The user brings (a) an agent hosted on AWS Bedrock AgentCore Runtime, and
(b) a task specification with eval dataset + grader. This vertical runs the
EXISTING auto-research optimization loop to improve the agent's config
(system_prompt, few_shot, temperature, etc.) WITHOUT modifying any frozen contract.

DESIGN PRINCIPLE (Issue #28 — the benchmark paradox):
The judge is the REFEREE. It imports NO LLM client. It grounds truth ONLY in:
  1. User-planted held-out labels (the answer key)
  2. Deterministic graders (exact, regex, or pure callable)

The agent (the CONTESTANT) is measured only against its accuracy on the held-out
split. The proposer (agentic optimizer) receives ONLY the train split and can
NEVER see the holdout data or alter the grader/loss.

If a task requests an LLM-as-judge or soft rubric grading, this vertical REFUSES
— the paradox remains human territory.
"""

import json
import os

from .agentcore_client import AgentCoreInvoker, StubAgent
from .actions import BYOAgentActions
from .judge import BYOAgentBenchmark
from .loss_spec import build_loss_spec, freeze_loss, hash_grader_dataset
from .pore import BYOAgentPore
from .proposer import BYOAgentProposer, ScriptedProposer

__all__ = [
    "AgentCoreInvoker",
    "StubAgent",
    "BYOAgentActions",
    "BYOAgentBenchmark",
    "BYOAgentPore",
    "BYOAgentProposer",
    "ScriptedProposer",
    "build_loss_spec",
    "freeze_loss",
    "hash_grader_dataset",
    "build_env_from_task",
]


def build_env_from_task(task_dict: dict, proposer_use_claude: bool = False) -> dict:
    """Build a domain env dict from a BYO-Agent task specification.

    Args:
        task_dict: Dict with:
            - objective: str
            - agent_ref: str ("stub" or AWS runtime ARN)
            - eval_ref: path to JSONL file (lines with {input, expected})
            - grader: {"kind": "exact"|"regex"|"programmatic", "params": {...}}
            - constraints: {"max_iterations": int, "token_price": float}
        proposer_use_claude: If True, use BYOAgentProposer (needs ANTHROPIC_API_KEY).
                           If False, use ScriptedProposer (deterministic, offline).

    Returns:
        Domain env dict ready for run_loop:
          {
            "_cur_config": {system_prompt, few_shot, temperature, ...},
            "_agent": AgentCoreInvoker or StubAgent,
            "_eval": {"train": [...], "holdout": [...]},
            "_grader": (kind, callable),
            "_loss_hash": str,
            "_logclient": (injected by dispatcher, None here),
            "_config_stack": [],
          }

    Raises:
        ValueError: If task_dict is malformed or grader kind is unsupported.
    """
    objective = task_dict.get("objective", "(No objective)")
    agent_ref = task_dict.get("agent_ref", "stub")
    eval_ref = task_dict.get("eval_ref", "")
    grader_spec = task_dict.get("grader", {"kind": "exact"})
    constraints = task_dict.get("constraints", {})

    # Load eval dataset from JSONL file.
    eval_data = _load_eval_jsonl(eval_ref)
    if not eval_data:
        raise ValueError(f"Could not load eval data from {eval_ref}")

    # Split into train/holdout (80/20 split by default).
    train_holdout = _split_train_holdout(eval_data, train_fraction=0.7)

    # Build grader.
    grader_kind = grader_spec.get("kind", "exact")
    if grader_kind == "exact":
        grader = (grader_kind, BYOAgentBenchmark._exact_grader)
    elif grader_kind == "regex":
        pattern = grader_spec.get("params", {}).get("pattern", ".*")
        grader = (grader_kind, BYOAgentBenchmark._regex_grader(pattern))
    elif grader_kind == "programmatic":
        raise ValueError(
            "Programmatic grader requires a callable; not yet supported in this builder. "
            "Use exact or regex, or call build_env_from_task with custom grader injection."
        )
    else:
        raise ValueError(
            f"Unsupported grader kind '{grader_kind}'. "
            f"Must be exact|regex|programmatic. LLM-as-judge is NOT allowed (Issue #28)."
        )

    # Instantiate agent.
    if agent_ref == "stub":
        agent = StubAgent()
    else:
        # Assume it's an AWS Bedrock runtime ARN.
        agent = AgentCoreInvoker(runtime_arn=agent_ref)

    # Build initial config (deliberately suboptimal to show improvement).
    initial_config = {
        "system_prompt": "Answer the question.",
        "few_shot": [],
        "temperature": 1.5,
        "top_p": 1.0,
        "max_tokens": 1024,
    }

    # Compute loss hash (for tampering detection).
    loss_hash = hash_grader_dataset(grader, train_holdout)

    # Build env dict.
    env = {
        "_cur_config": initial_config,
        "_agent": agent,
        "_eval": train_holdout,
        "_grader": grader,
        "_loss_hash": loss_hash,
        "_logclient": None,  # injected by dispatcher
        "_config_stack": [],
    }

    return env


def _load_eval_jsonl(path: str) -> list[dict]:
    """Load eval data from a JSONL file.

    Each line is a JSON object with {input, expected}.

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


def _split_train_holdout(
    data: list[dict], train_fraction: float = 0.7
) -> dict:
    """Split eval data into train and holdout sets (DETERMINISTICALLY seeded).

    CRITICAL FOR ISSUE #28 FROZEN LOSS: The split is NOT random. It is seeded
    deterministically from the dataset content hash, so:
      - Same eval data → same split every run (reproducible)
      - Different eval data → different split (no accidental reuse)

    This ensures frozen-loss benchmarks are reproducible across runs.

    Args:
        data: List of eval items.
        train_fraction: Fraction for train set (default 0.7 = 70% train, 30% holdout).

    Returns:
        Dict with 'train' and 'holdout' keys, with train ∩ holdout = ∅.
    """
    if not data:
        return {"train": [], "holdout": []}

    # Seed RNG from dataset content hash (deterministic across runs).
    import hashlib
    dataset_json = json.dumps(data, sort_keys=True)
    seed = int(hashlib.sha256(dataset_json.encode()).hexdigest()[:8], 16)

    # Use seeded RNG to shuffle indices deterministically.
    import random
    rng = random.Random(seed)
    indices = list(range(len(data)))
    rng.shuffle(indices)

    # Split the shuffled indices.
    split_idx = int(len(indices) * train_fraction)
    train_indices = sorted(indices[:split_idx])
    holdout_indices = sorted(indices[split_idx:])

    return {
        "train": [data[i] for i in train_indices],
        "holdout": [data[i] for i in holdout_indices],
    }
