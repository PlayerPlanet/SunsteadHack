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


def run_loop(
    task_spec: dict,
    *,
    proposer,
    benchmark,
    pore,
    logclient,
    iterations: int = 10,
) -> None:
    """Run the optimization loop.

    Args:
        task_spec: Task specification (e.g., {task_id, model, workload_id}).
        proposer: Object with propose(task_spec, history) -> Candidate method.
        benchmark: Module with run_benchmark, check_correctness, is_within_noise.
        pore: Module with evaluate(candidate) -> PoreResult function.
        logclient: LogClient protocol for write_experiment, write_crossing, etc.
        iterations: Number of optimization iterations.

    Raises:
        NotImplementedError: Story A owns this implementation.
    """
    raise NotImplementedError("run_loop — owned by Story A, GitHub issue #2")
