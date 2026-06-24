"""Main optimization loop — propose, gate, apply, benchmark, decide.

Story A (GitHub issue #2) owns the loop implementation.

Control flow:
  1. proposer.propose(task_spec, history) -> Candidate
  2. pore.evaluate(candidate) -> PoreResult
  3. If escalated, write to logclient; continue
  4. actions.apply(conn, candidate) -> None
  5. benchmark.run_benchmark(conn, workload) -> Result
  6. is_within_noise(baseline, candidate) -> bool decision
  7. Decide: keep / discard / rollback
  8. logclient.write_experiment(...)
  9. Repeat or exit
"""

from dataclasses import asdict

from cleanroom import actions as _default_actions


def run_loop(
    task_spec: dict,
    *,
    proposer,
    benchmark,
    pore,
    logclient,
    actions=None,
    iterations: int = 10,
) -> None:
    """Run the optimization loop.

    Establishes a baseline on the first iteration, then proposes, gates, applies,
    benchmarks, and decides on each successive iteration. Tracks accepted candidates
    in `history` for the proposer to consider.

    Args:
        task_spec: Task specification (e.g., {task_id, model, workload_id, conn}).
        proposer: Object with propose(task_spec, history) -> Candidate method.
        benchmark: Object with run_benchmark, check_correctness, is_within_noise methods.
        pore: Object with evaluate(candidate) -> PoreResult method.
        logclient: LogClient protocol for write_experiment, write_crossing, etc.
        actions: Action adapter exposing apply(conn, candidate) / rollback(conn, candidate).
            Defaults to cleanroom.actions (index/guc). Domain benchmarks (epic #8 —
            quant/bio/kernel) inject their own adapter so the same loop drives a
            different action space without changing this function.
        iterations: Number of optimization iterations (default 10).

    Raises:
        ValueError: If required fields are missing from task_spec or other contracts fail.
    """
    _actions = actions if actions is not None else _default_actions
    # TODO(integration#1): settle conn sourcing with Story B
    # For now, allow None (Phase-0 fixtures) or real connection from task_spec
    conn = task_spec.get("conn")

    # Initialize baseline and history
    baseline = None
    history = []

    for iteration in range(iterations):
        # Iteration 1: Establish baseline
        if iteration == 0:
            # Run a benchmark on the initial state to establish baseline
            # (no candidate applied yet; this is the "status quo" before any optimization)
            baseline_result = benchmark.run_benchmark(
                conn, task_spec.get("workload_id", ""), warmup=5, trials=10
            )
            baseline = {
                "p99_ms": baseline_result.p99_ms,
                "samples": baseline_result.samples,
            }
            continue

        # Iteration 2+: Propose, gate, apply, benchmark, decide
        candidate = proposer.propose(task_spec, history)

        pore_result = pore.evaluate(candidate)

        # Gate 1: Check pore escalation
        if pore_result.requires_human_judgment or pore_result.decision == "escalate":
            # Write experiment with decision="escalated", write crossing, skip apply/benchmark
            exp_id = logclient.write_experiment(
                task_id=task_spec.get("task_id", ""),
                model=task_spec.get("model", "stub"),
                drift_level=task_spec.get("drift_level", 0),
                candidate=asdict(candidate),
                baseline_p99=baseline["p99_ms"],
                candidate_p99=None,
                cost_estimate=None,
                correctness_ok=None,
                within_noise=None,
                decision="escalated",
            )
            logclient.write_crossing(
                experiment_id=exp_id,
                pore=pore_result.pore,
                risk_level=pore_result.risk_level,
                requires_human_judgment=pore_result.requires_human_judgment,
                action={"candidate": asdict(candidate)},
            )
            continue

        # Apply candidate
        _actions.apply(conn, candidate)

        # Run benchmark
        result = benchmark.run_benchmark(
            conn, task_spec.get("workload_id", ""), warmup=5, trials=10
        )

        # Check correctness
        correctness_ok = benchmark.check_correctness(conn, candidate)

        # Decide
        within_noise = benchmark.is_within_noise(baseline["samples"], result.samples)

        if result.p99_ms > baseline["p99_ms"]:
            # Regression
            decision = "rollback"
            _actions.rollback(conn, candidate)
        elif within_noise:
            # Improvement but within noise
            decision = "discard"
            _actions.rollback(conn, candidate)
        elif not correctness_ok:
            # Correctness failure
            decision = "rollback"
            _actions.rollback(conn, candidate)
        else:
            # Genuine improvement
            decision = "keep"
            baseline = {
                "p99_ms": result.p99_ms,
                "samples": result.samples,
            }
            history.append(candidate)

        # Log the experiment
        logclient.write_experiment(
            task_id=task_spec.get("task_id", ""),
            model=task_spec.get("model", "stub"),
            drift_level=task_spec.get("drift_level", 0),
            candidate=asdict(candidate),
            baseline_p99=baseline["p99_ms"],
            candidate_p99=result.p99_ms,
            cost_estimate=result.cost_estimate,
            correctness_ok=correctness_ok,
            within_noise=within_noise,
            decision=decision,
        )
