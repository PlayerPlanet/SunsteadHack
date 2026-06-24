"""Domain benchmark adapters for Epic #8 — autoresearch beyond Postgres.

Each sub-package implements the frozen judge contract:
    benchmark.run_benchmark(env, workload_id, *, warmup, trials) -> Result
    benchmark.check_correctness(env, candidate) -> bool
    benchmark.is_within_noise(baseline_samples, candidate_samples) -> bool
    pore.evaluate(candidate) -> PoreResult
    actions.apply(env, candidate) / actions.rollback(env, candidate)

Pass the domain's actions adapter to run_loop(..., actions=<adapter>).
"""
