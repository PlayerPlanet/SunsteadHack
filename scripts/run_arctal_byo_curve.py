"""Arctal green-bond agent optimization curve runner.

Demonstrates the byo_agent vertical on a real domain-specific agent (arctal).
Tests both deterministic (rule) and LLM-based (llm) modes.

Usage:
    uv run python scripts/run_arctal_byo_curve.py --mode rule --iterations 8
    uv run python scripts/run_arctal_byo_curve.py --mode llm --iterations 8
"""

import argparse
import json
import os
import sys

from cleanroom.loop import run_loop
from cleanroom.fixtures import InMemoryLogClient
from cleanroom.domains.byo_agent import (
    BYOAgentBenchmark,
    BYOAgentActions,
    BYOAgentPore,
    build_loss_spec,
    freeze_loss,
    _split_train_holdout,
)
from cleanroom.domains.byo_agent.adapters import (
    ArctalReviewAgent,
    ArctalPromptProposer,
    build_arctal_eval,
    write_arctal_eval_jsonl,
)


def run_arctal_byo_curve(mode: str = "rule", iterations: int = 8, seed: int = 7, model: str = "claude-haiku-4-5-20251001"):
    """Run the Arctal BYO-Agent optimization curve.

    Args:
        mode: "rule" (deterministic) or "llm" (calls Anthropic).
        iterations: Number of optimization iterations.
        seed: Random seed for deterministic eval generation.
        model: Model ID for LLM mode.

    Returns:
        List of experiment dicts from logclient.
    """
    # Step 1: Build and write arctal eval dataset (deterministic, seed-based).
    print(f"\n[1] Building arctal eval (seed={seed}, mode={mode})...")
    eval_data = build_arctal_eval(seed=seed)
    print(f"    Generated {len(eval_data)} claims")

    # Count labels.
    labels = {"ok": 0, "error": 0, "escalate": 0}
    for item in eval_data:
        labels[item["expected"]] += 1
    print(f"    Label distribution: ok={labels['ok']}, error={labels['error']}, escalate={labels['escalate']}")

    # Write fixture.
    fixture_path = "cleanroom/domains/byo_agent/fixtures/arctal_eval.jsonl"
    os.makedirs(os.path.dirname(fixture_path), exist_ok=True)
    write_arctal_eval_jsonl(fixture_path, seed=seed)
    print(f"    Fixture written to {fixture_path}")

    # Step 2: Split into train/holdout (deterministic, seeded from content hash).
    split = _split_train_holdout(eval_data, train_fraction=0.7)
    print(f"\n[2] Split data: train={len(split['train'])}, holdout={len(split['holdout'])}")

    # Step 3: Build the agent.
    print(f"\n[3] Building Arctal agent (mode={mode})...")
    agent = ArctalReviewAgent(mode=mode, model=model)

    # Step 4: Build env.
    initial_config = {
        "system_prompt": "You are a green-bond auditor. Review claims for accuracy.",
        "few_shot": [],
        "temperature": 0.0 if mode == "rule" else 0.3,
        "top_p": 1.0,
        "max_tokens": 256,
    }

    grader = ("exact", BYOAgentBenchmark._exact_grader)
    from cleanroom.domains.byo_agent import hash_grader_dataset
    loss_hash = hash_grader_dataset(grader, split)

    env = {
        "_cur_config": initial_config,
        "_agent": agent,
        "_eval": split,
        "_grader": grader,
        "_loss_hash": loss_hash,
        "_logclient": None,
        "_config_stack": [],
    }

    # Step 5: Create logclient and freeze loss.
    logclient = InMemoryLogClient()
    env["_logclient"] = logclient

    task_id = f"arctal-byo-{mode}"
    loss_spec = build_loss_spec(
        objective="Optimize arctal agent config to detect green-bond data errors (arithmetic + semantic).",
        grader=grader,
        dataset=split,
        action_space=["agent_config"],
        gameability_review=[
            "Eval data: deterministic, seeded from content hash, never altered",
            "Agent: arctal review agent (rule | llm mode)",
            "Grader: exact match (deterministic)",
            "Proposer: deterministic prompt ladder (ArctalPromptProposer)",
            "Loss definition: frozen before iteration 0 (Issue #28)",
        ],
    )
    freeze_loss(logclient, task_id, loss_spec)
    print(f"    Loss frozen: hash={loss_hash[:16]}...")

    # Step 6: Build proposer and run the loop.
    print(f"\n[4] Running optimization loop ({iterations} iterations)...")
    proposer = ArctalPromptProposer()

    run_loop(
        task_spec={
            "task_id": task_id,
            "model": mode,
            "workload_id": f"arctal-{mode}",
            "conn": env,
        },
        proposer=proposer,
        benchmark=BYOAgentBenchmark(),
        pore=BYOAgentPore(),
        logclient=logclient,
        actions=BYOAgentActions(),
        iterations=iterations,
    )

    return logclient.read_experiments()


def summarize(task_id: str, exps, eval_data):
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

    # Count holdout accuracy by label subset.
    # (In a real scenario, we'd re-run holdout and track per-subset accuracy.)
    label_counts = {"ok": 0, "error": 0, "escalate": 0}
    for item in eval_data:
        label_counts[item["expected"]] += 1

    return {
        "task_id": task_id,
        "experiments": len(exps),
        "baseline_error": baseline_p99,
        "best_error": best_p99,
        "improvement_pct": improvement,
        "decisions": decisions,
        "label_distribution": label_counts,
    }


def print_task_report(name: str, summary: dict):
    """Print a summary report."""
    d = summary["decisions"]
    labs = summary.get("label_distribution", {})
    print(f"\n-- [{name}] Arctal BYO-Agent Result ---------------------------------")
    print(f"   experiments logged : {summary['experiments']}")
    if summary["baseline_error"] is not None:
        print(f"   baseline error     : {summary['baseline_error']:.4f}")
    if summary["best_error"] is not None:
        print(f"   best error         : {summary['best_error']:.4f}")
    if summary["improvement_pct"] is not None:
        print(f"   improvement        : {summary['improvement_pct']:+.1f}%")
    print(
        f"   decisions          : "
        f"keep={d.get('keep',0)} discard={d.get('discard',0)} "
        f"rollback={d.get('rollback',0)} escalated={d.get('escalated',0)}"
    )
    if labs:
        print(f"   eval label dist    : ok={labs.get('ok',0)} error={labs.get('error',0)} escalate={labs.get('escalate',0)}")


def print_curve(exps):
    """Print the error-rate curve iteration by iteration."""
    print("\n-- Error-rate curve (per iteration) ---------------------------------")
    for i, e in enumerate(exps):
        baseline_p99 = e.get("baseline_p99")
        candidate_p99 = e.get("candidate_p99")
        decision = e.get("decision", "?")
        if baseline_p99 is not None:
            print(f"  {i:2d}. baseline={baseline_p99:.4f} > candidate={candidate_p99:.4f} [{decision}]")


def print_loss_definition(exps):
    """Print loss-definition freeze record."""
    for e in exps:
        if e.get("decision") == "freeze":
            print(f"\n-- Loss Definition (Frozen) ------------------------------------------")
            payload = e.get("candidate", {}).get("payload", {})
            content_hash = payload.get("content_hash", "?")
            print(f"   content_hash       : {content_hash[:32]}...")
            print(f"   domain             : {payload.get('domain', '?')}")
            print(f"   objective          : {payload.get('objective', '?')}")
            print(f"   [OK] Loss frozen before iteration 0")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Arctal BYO-Agent optimization curve"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["rule", "llm"],
        default="rule",
        help="Agent mode: 'rule' (deterministic) or 'llm' (calls Anthropic)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=8,
        help="Number of optimization iterations",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Random seed for eval generation",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-haiku-4-5-20251001",
        help="Model ID for LLM mode",
    )
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print(f"Arctal BYO-Agent Optimization Curve ({args.mode.upper()} mode)")
    print("=" * 70)

    try:
        exps = run_arctal_byo_curve(
            mode=args.mode,
            iterations=args.iterations,
            seed=args.seed,
            model=args.model,
        )

        # Rebuild eval for summary (deterministic, same seed).
        eval_data = build_arctal_eval(seed=args.seed)

        summary = summarize(f"arctal-{args.mode}", exps, eval_data)
        print_loss_definition(exps)
        print_task_report(f"arctal-{args.mode}", summary)
        print_curve(exps)

        print("\n[OK] Curve generation successful")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
