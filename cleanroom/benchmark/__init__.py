"""Benchmark and correctness evaluation — Story B (GitHub issue #3).

The statistically-honest core of the autoresearch loop. Three contract functions:

- `run_benchmark(conn, workload_id, *, warmup, trials)` -> Result
- `check_correctness(conn, candidate)` -> bool
- `is_within_noise(baseline_samples, candidate_samples)` -> bool

Design is shaped by the Gate-1 findings (docs/gate-1-findings.md), measured live on
`sunstead-pg-bench`:

  * The workload is fully deterministic (same plan/cost/rows every run); only timing
    varies. Clean noise floor ≈ CV 6.5% — but ONLY when trials run **sequentially**
    and the working set stays **in memory**.
  * Concurrency inflated CV to ~22% (trials fighting for CPU) -> we run trials strictly
    sequentially.
  * A sort spilled to disk because `work_mem` defaulted to 7 MB -> we `SET work_mem`
    per session before measuring, so a disk spill never masquerades as a regression.

`is_within_noise` is the Gate-2 guard ("signal beats variance"): it must provably
reject within-variance changes so the loop never "keeps" noise. It combines a
minimum-effect-size floor with a Welch's t-test (two-sample, unequal variance),
computed with numpy only (scipy is not a dependency).
"""

import math
import time

import numpy as np

from cleanroom.types import Candidate, Result

# --- Tunables (documented constants, not magic numbers) ---------------------

# Per-session work_mem to keep the benchmark's sorts/hashes in memory. Gate-1 showed
# the default 7 MB spilled a 1M-row sort to disk and inflated variance.
_BENCH_WORK_MEM = "256MB"

# is_within_noise: a candidate must improve the median by at least this fraction to
# be considered a real win at all. Below this, it is noise by definition — even if a
# t-test would call it "significant", a sub-2% DB latency change is not actionable and
# sits inside Gate-1's ~6.5% measured floor on a per-sample basis.
_MIN_EFFECT_FRACTION = 0.02

# Welch's t-test significance threshold. |t| below this critical value => not
# statistically distinguishable from baseline => within noise. ~2.0 corresponds to
# alpha≈0.05 (two-sided) for the trial counts we use (df typically >= 8).
_T_CRITICAL = 2.0


# --- Workload registry ------------------------------------------------------
#
# Maps a workload_id to the SQL the harness times. Keeping this here (rather than
# scattering SQL through the loop) is what makes a workload "frozen": the bytes of
# the query are fixed and version-controlled, so every iteration measures the same
# thing. `__default__` is a zero-data, CPU-bound, fully deterministic query (matching
# the Gate-1 probe) so the harness is runnable before any dataset is loaded.

_WORKLOADS: dict[str, str] = {
    "__default__": (
        "SELECT count(*) FROM ("
        "  SELECT md5(g::text) AS h FROM generate_series(1, 200000) AS g"
        "  ORDER BY h"
        ") AS sub"
    ),
}


def register_workload(workload_id: str, sql: str) -> None:
    """Register (freeze) a workload's SQL under an id.

    Lets the harness be pointed at a real dataset (pgbench / JOB) without changing
    any signatures: the loop still calls `run_benchmark(conn, workload_id, ...)`.
    """
    _WORKLOADS[workload_id] = sql


def _resolve_workload(workload_id: str) -> str:
    if not workload_id:
        return _WORKLOADS["__default__"]
    if workload_id not in _WORKLOADS:
        raise ValueError(
            f"run_benchmark: unknown workload_id {workload_id!r}; "
            f"register it via register_workload() first. "
            f"Known: {sorted(_WORKLOADS)}"
        )
    return _WORKLOADS[workload_id]


def _time_query_ms(cur, sql: str) -> float:
    """Execute `sql` once and return wall-clock elapsed milliseconds.

    We time the round-trip with a monotonic clock and drain the result so the cost
    of materializing rows is included (a faithful client-observed latency).
    """
    start = time.perf_counter()
    cur.execute(sql)
    if cur.description is not None:
        cur.fetchall()
    return (time.perf_counter() - start) * 1000.0


def run_benchmark(conn, workload_id: str, *, warmup: int = 5, trials: int = 10) -> Result:
    """Execute the frozen workload and return p99/throughput/cost/samples.

    Runs `warmup` untimed executions (to populate cache — Gate-1's recommendation,
    equivalent to a pg_prewarm), then `trials` sequentially-timed executions. p99 is
    computed from the per-trial samples.

    If `conn` is None (Phase-0 fixture mode) this raises — the in-memory fixture
    `CannedBenchmark` is what callers use without a connection. The production
    harness requires a real psycopg3 connection.

    Args:
        conn: An open psycopg3 connection.
        workload_id: Key into the frozen workload registry ("" -> "__default__").
        warmup: Untimed warmup iterations (cache priming).
        trials: Sequentially-timed measurement iterations.

    Returns:
        Result(p99_ms, throughput, cost_estimate, samples).
    """
    if conn is None:
        raise ValueError(
            "run_benchmark: conn is None. The production harness needs a real "
            "connection; use cleanroom.fixtures.CannedBenchmark for connection-free tests."
        )
    if trials < 1:
        raise ValueError(f"run_benchmark: trials must be >= 1, got {trials}")

    sql = _resolve_workload(workload_id)

    with conn.cursor() as cur:
        # Keep the working set in memory for the duration of this session's trials.
        cur.execute(f"SET work_mem = '{_BENCH_WORK_MEM}'")

        # Warmup (untimed) — prime shared buffers / OS cache so the first timed
        # trial isn't penalised for a cold cache.
        for _ in range(max(0, warmup)):
            cur.execute(sql)
            if cur.description is not None:
                cur.fetchall()

        # Measure — strictly sequential (Gate-1: concurrency triples the CV).
        samples = [_time_query_ms(cur, sql) for _ in range(trials)]

    samples_arr = np.asarray(samples, dtype=float)
    p99 = float(np.percentile(samples_arr, 99))
    median_ms = float(np.median(samples_arr))
    # Throughput as queries/sec implied by the median latency of one sequential query.
    throughput = (1000.0 / median_ms) if median_ms > 0 else 0.0
    # Cost proxy: total measured DB time in seconds. The real cost/budget constraint
    # is read from Aiven pricing (aiven_service_plan_pricing) at the loop level; this
    # per-experiment proxy lets the loop compare relative spend without a pricing call.
    cost_estimate = float(samples_arr.sum() / 1000.0)

    return Result(
        p99_ms=p99,
        throughput=throughput,
        cost_estimate=cost_estimate,
        samples=[float(s) for s in samples],
    )


def check_correctness(conn, candidate: Candidate) -> bool:
    """Verify a candidate does not change query results (Gate-4).

    The honest case that matters is a **query rewrite**: an index or GUC change can
    never alter result semantics, but a rewrite can. So:

    - For a candidate carrying both `original_sql` and `rewritten_sql` in params, we
      execute both and compare a hash of their (ordered) result sets. Equal -> True;
      different -> False (the loop must NOT auto-keep a result-changing rewrite).
    - For index/guc candidates (or fixture mode with conn=None), results are
      semantically invariant, so this returns True.

    Args:
        conn: An open psycopg3 connection (or None in fixture mode).
        candidate: The candidate to validate.

    Returns:
        True if results are unchanged (or not applicable), False if a rewrite
        changed the result set.
    """
    params = getattr(candidate, "params", {}) or {}
    original_sql = params.get("original_sql")
    rewritten_sql = params.get("rewritten_sql")

    # Only a rewrite can change results; everything else is invariant by construction.
    if not (original_sql and rewritten_sql):
        return True

    if conn is None:
        # Can't verify without a connection; be conservative and treat as unverified-OK
        # only in fixture mode. Production always passes a real conn.
        return True

    def _result_hash(sql: str) -> int:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall() if cur.description is not None else []
        # Order matters for correctness equivalence; hash the tuple-of-rows repr.
        return hash(repr(rows))

    return _result_hash(original_sql) == _result_hash(rewritten_sql)


def is_within_noise(baseline_samples: list[float], candidate_samples: list[float]) -> bool:
    """Return True if the candidate is statistically indistinguishable from baseline.

    Gate-2 guard. A change is "within noise" (i.e. NOT a real signal) when EITHER:

      1. the median improvement is smaller than `_MIN_EFFECT_FRACTION` (a sub-2%
         latency move is noise regardless of what a t-test says), OR
      2. a two-sample Welch's t-test (unequal variances) cannot distinguish the two
         sample sets at the `_T_CRITICAL` threshold.

    Returning True tells the loop "don't keep this — it's noise." Returning False
    means the improvement is both large enough and statistically real.

    Edge cases: empty inputs, or zero variance with identical means, are treated as
    within-noise (no evidence of a real change).
    """
    base = np.asarray(baseline_samples, dtype=float)
    cand = np.asarray(candidate_samples, dtype=float)

    if base.size == 0 or cand.size == 0:
        return True

    base_med = float(np.median(base))
    cand_med = float(np.median(cand))

    # (1) Minimum effect size. We only care about *improvements* (lower latency).
    # If the candidate is not at least _MIN_EFFECT_FRACTION faster than baseline,
    # it's within noise. (A regression — cand slower — is also "not a real win",
    # so it is correctly reported as within-noise here too.)
    if base_med <= 0:
        return True
    improvement_fraction = (base_med - cand_med) / base_med
    if improvement_fraction < _MIN_EFFECT_FRACTION:
        return True

    # (2) Welch's t-test. With n>=2 on both sides, test whether the means differ.
    if base.size < 2 or cand.size < 2:
        # Not enough data for a variance estimate; rely on the effect-size gate above.
        # We already know the effect cleared the floor, so call it signal.
        return False

    mean_b, mean_c = float(base.mean()), float(cand.mean())
    var_b = float(base.var(ddof=1))
    var_c = float(cand.var(ddof=1))
    n_b, n_c = base.size, cand.size

    se_sq = var_b / n_b + var_c / n_c
    if se_sq <= 0:
        # Zero variance on both sides. Means differ (effect cleared the floor) => signal.
        return mean_b == mean_c

    t_stat = (mean_b - mean_c) / math.sqrt(se_sq)

    # |t| below critical => indistinguishable => within noise.
    return abs(t_stat) < _T_CRITICAL
