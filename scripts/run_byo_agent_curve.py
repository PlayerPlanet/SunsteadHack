"""BYO-Agent optimization curve runner — demonstrates the vertical offline.

Uses StubAgent + ScriptedProposer to produce a descending error-rate curve,
showing that the loop successfully optimizes agent configs.

Usage:
    uv run python scripts/run_byo_agent_curve.py
    uv run python scripts/run_byo_agent_curve.py --iterations 15
"""

import argparse
import json
import os

from cleanroom.loop import run_loop
from cleanroom.fixtures import InMemoryLogClient
from cleanroom.domains.byo_agent import (
    build_env_from_task,
    BYOAgentBenchmark,
    BYOAgentActions,
    BYOAgentPore,
    ScriptedProposer,
)


def run_byo_agent_task(task_file: str, iterations: int = 10):
    """Run the BYO-Agent vertical with a demo task.

    Args:
        task_file: Path to task JSON file.
        iterations: Number of optimization iterations.

    Returns:
        List of experiment dicts from the logclient.
    """
    # Load task spec from JSON.
    with open(task_file, "r") as f:
        task_dict = json.load(f)

    # Build the domain env (includes agent, eval dataset, grader).
    # The task_file path is relative; resolve it.
    eval_ref = task_dict.get("eval_ref", "")
    if eval_ref and not os.path.isabs(eval_ref):
        # Make it relative to the repo root.
        repo_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        eval_ref = os.path.join(repo_root, eval_ref)
        task_dict["eval_ref"] = eval_ref

    env = build_env_from_task(task_dict, proposer_use_claude=False)

    # Verify the env is valid.
    if env["_agent"] is None:
        raise ValueError("Failed to create agent")
    if not env["_eval"]["holdout"]:
        raise ValueError("No holdout eval data loaded")

    # Create logclient.
    logclient = InMemoryLogClient()
    env["_logclient"] = logclient

    # Freeze the loss before iteration 0.
    from cleanroom.domains.byo_agent import build_loss_spec, freeze_loss

    loss_spec = build_loss_spec(
        objective=task_dict.get("objective", ""),
        grader=env["_grader"],
        dataset=env["_eval"],
        action_space=task_dict.get("action_space", []),
        gameability_review=[
            "Stub agent: error improves with 'expert'/'careful'/'precise' in prompt",
            "Held-out split: 30% of data, never shown to proposer",
            "Grader: exact match (deterministic, no LLM paradox)",
        ],
    )
    freeze_loss(logclient, task_dict["task_id"], loss_spec)

    # Run the loop with scripted proposer.
    run_loop(
        task_spec={
            "task_id": task_dict["task_id"],
            "model": "scripted",
            "workload_id": task_dict.get("workload_id", ""),
            "conn": env,
        },
        proposer=ScriptedProposer(),
        benchmark=BYOAgentBenchmark(),
        pore=BYOAgentPore(),
        logclient=logclient,
        actions=BYOAgentActions(),
        iterations=iterations,
    )

    return logclient.read_experiments()


def summarize(task_id: str, exps):
    """Reduce experiment log to summary."""
    decisions = {}
    for e in exps:
        decisions[e["decision"]] = decisions.get(e["decision"], 0) + 1

    baseline_p99 = exps[0]["baseline_p99"] if exps else None
    cand_p99s = [e["candidate_p99"] for e in exps if e.get("candidate_p99") is not None]
    best_p99 = min(cand_p99s) if cand_p99s else None

    # Improvement (lower p99 = better, so negative improvement is good).
    improvement = None
    if baseline_p99 and best_p99 is not None and baseline_p99 > 0:
        improvement = (baseline_p99 - best_p99) / baseline_p99 * 100.0

    # Never keep an incorrect candidate (core honesty invariant).
    bad_keeps = [e for e in exps if e["decision"] == "keep" and e.get("correctness_ok") is False]

    return {
        "task_id": task_id,
        "experiments": len(exps),
        "baseline_loss": baseline_p99,
        "best_loss": best_p99,
        "improvement_pct": improvement,
        "decisions": decisions,
        "bad_keeps": len(bad_keeps),
    }


def print_task_report(name: str, summary: dict):
    """Print a summary report."""
    d = summary["decisions"]
    print(f"\n-- [{name}] BYO-Agent demo ------------------------------------------")
    print(f"   experiments logged : {summary['experiments']}")
    if summary["baseline_loss"] is not None:
        print(f"   baseline error     : {summary['baseline_loss']:.4f}")
    if summary["best_loss"] is not None:
        print(f"   best error         : {summary['best_loss']:.4f}")
    if summary["improvement_pct"] is not None:
        print(f"   improvement        : {summary['improvement_pct']:+.1f}%")
    print(
        f"   decisions          : "
        f"keep={d.get('keep',0)} discard={d.get('discard',0)} "
        f"rollback={d.get('rollback',0)} escalated={d.get('escalated',0)}"
    )
    invariant = "OK" if summary["bad_keeps"] == 0 else f"VIOLATED ({summary['bad_keeps']})"
    print(f"   never-keep-wrong   : {invariant}")


def print_curve(exps):
    """Print the error-rate curve iteration by iteration."""
    print("\n-- Error-rate curve (per iteration) ---------------------------------")
    for i, e in enumerate(exps):
        baseline_p99 = e.get("baseline_p99")
        candidate_p99 = e.get("candidate_p99")
        decision = e.get("decision", "?")
        if baseline_p99 is not None:
            print(f"  {i:2d}. baseline={baseline_p99:.4f} > candidate={candidate_p99:.4f} [{decision}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the BYO-Agent optimization curve demo"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of optimization iterations",
    )
    parser.add_argument(
        "--task",
        type=str,
        default="cleanroom/control/tasks/byo-agent-demo.json",
        help="Path to task JSON file",
    )
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("BYO-Agent Optimization Curve (Demo)")
    print("=" * 70)

    try:
        exps = run_byo_agent_task(args.task, iterations=args.iterations)
        summary = summarize("byo-agent-demo", exps)
        print_task_report("byo-agent-demo", summary)
        print_curve(exps)
        print("\n[OK] Curve generation successful")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        exit(1)
