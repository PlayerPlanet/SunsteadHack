"""Kernel optimization benchmark — numerical-equivalence + timing judge.

Domain: matrix multiply (32×32) in pure Python.
Objective: p99 wall-clock latency (lower = better; native fit, no remapping).
Judge: correctness-gated timing — check_correctness runs allclose FIRST;
       a kernel that is fast but numerically wrong is NEVER kept.

The proposer can never see or alter reference_out, so it cannot fake speed
without correctness — "can't grade its own homework" in its purest form.

Epic #8 / Issue #9.
"""

import random
import time
import statistics as _stats

from cleanroom.types import Candidate, Result, PoreResult

# ── Fixed benchmark inputs (seeded, never exposed to the proposer) ──────────

_N = 32  # matrix dimension — large enough for detectable timing diffs in pure Python


def _make_matrix(n: int, seed: int) -> list[list[float]]:
    rng = random.Random(seed)
    return [[rng.gauss(0.0, 1.0) for _ in range(n)] for _ in range(n)]


_REF_A = _make_matrix(_N, seed=42)
_REF_B = _make_matrix(_N, seed=43)


# ── Kernel variants ──────────────────────────────────────────────────────────

def _naive(A: list, B: list) -> list[list[float]]:
    """i,j,k order — many cold B-column accesses; the slow reference."""
    n = len(A)
    C = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            for k in range(n):
                C[i][j] += A[i][k] * B[k][j]
    return C


def _row_order(A: list, B: list) -> list[list[float]]:
    """i,k,j with hoisted A[i][k] — saves one list lookup per inner j."""
    n = len(A)
    C = [[0.0] * n for _ in range(n)]
    for i in range(n):
        Ci = C[i]
        for k in range(n):
            aik = A[i][k]
            Bk = B[k]
            for j in range(n):
                Ci[j] += aik * Bk[j]
    return C


def _tiled(A: list, B: list, tile: int = 8) -> list[list[float]]:
    """Blocked/tiled — better cache locality for larger matrices."""
    n = len(A)
    C = [[0.0] * n for _ in range(n)]
    for i0 in range(0, n, tile):
        for k0 in range(0, n, tile):
            for j0 in range(0, n, tile):
                for i in range(i0, min(i0 + tile, n)):
                    Ci = C[i]
                    for k in range(k0, min(k0 + tile, n)):
                        aik = A[i][k]
                        Bk = B[k]
                        for j in range(j0, min(j0 + tile, n)):
                            Ci[j] += aik * Bk[j]
    return C


def _comprehension(A: list, B: list) -> list[list[float]]:
    """Transposed B + list comprehension sum — typically fastest in CPython."""
    n = len(A)
    BT = [[B[k][j] for k in range(n)] for j in range(n)]
    return [
        [sum(A[i][k] * BT[j][k] for k in range(n)) for j in range(n)]
        for i in range(n)
    ]


KERNELS: dict = {
    "naive": _naive,
    "row_order": _row_order,
    "tiled_8": lambda A, B: _tiled(A, B, tile=8),
    "comprehension": _comprehension,
}

# Reference output (frozen — the proposer never reads this)
_REFERENCE_OUT: list[list[float]] = _comprehension(_REF_A, _REF_B)


# ── Benchmark ────────────────────────────────────────────────────────────────

class KernelBenchmark:
    """Times the kernel stored in env['kernel_fn'] on fixed inputs."""

    def run_benchmark(self, env: dict, workload_id: str, *, warmup: int = 5, trials: int = 10) -> Result:
        fn = env.get("kernel_fn", KERNELS["naive"])
        for _ in range(warmup):
            fn(_REF_A, _REF_B)
        latencies = []
        for _ in range(trials):
            t0 = time.perf_counter()
            fn(_REF_A, _REF_B)
            latencies.append((time.perf_counter() - t0) * 1000.0)
        latencies.sort()
        p99 = latencies[max(0, int(0.99 * len(latencies)) - 1)]
        mean_ms = sum(latencies) / len(latencies)
        gflops = (2 * _N ** 3) / (mean_ms / 1000.0) / 1e9 if mean_ms > 0 else 0.0
        return Result(p99_ms=p99, throughput=gflops, cost_estimate=0.0, samples=latencies)

    def check_correctness(self, env: dict, candidate: Candidate) -> bool:
        """allclose vs. frozen reference — wrong kernels are NEVER kept."""
        fn = env.get("kernel_fn", KERNELS["naive"])
        out = fn(_REF_A, _REF_B)
        rtol, atol = 1e-5, 1e-8
        for i in range(_N):
            for j in range(_N):
                if abs(out[i][j] - _REFERENCE_OUT[i][j]) > atol + rtol * abs(_REFERENCE_OUT[i][j]):
                    return False
        return True

    def is_within_noise(self, baseline_samples: list, candidate_samples: list) -> bool:
        if not baseline_samples or not candidate_samples:
            return True
        bm = _stats.mean(baseline_samples)
        cm = _stats.mean(candidate_samples)
        bstd = _stats.stdev(baseline_samples) if len(baseline_samples) > 1 else 0.0
        cstd = _stats.stdev(candidate_samples) if len(candidate_samples) > 1 else 0.0
        combined = (bstd + cstd) / 2.0 or 0.5
        return abs(cm - bm) < combined


# ── Actions ──────────────────────────────────────────────────────────────────

class KernelActions:
    """Installs/uninstalls a kernel variant in env['kernel_fn']. No global mutation."""

    def apply(self, env: dict, candidate: Candidate) -> None:
        strategy = candidate.params.get("strategy", "naive")
        if strategy == "tiled":
            tile = candidate.params.get("tile_size", 8)
            env["kernel_fn"] = lambda A, B: _tiled(A, B, tile=tile)
        else:
            env["kernel_fn"] = KERNELS.get(strategy, KERNELS["naive"])
        env["_prev_strategy"] = env.get("_cur_strategy", "naive")
        env["_cur_strategy"] = strategy

    def rollback(self, env: dict, candidate: Candidate) -> None:
        prev = env.get("_prev_strategy", "naive")
        if prev == "tiled":
            tile = env.get("_prev_tile", 8)
            env["kernel_fn"] = lambda A, B: _tiled(A, B, tile=tile)
        else:
            env["kernel_fn"] = KERNELS.get(prev, KERNELS["naive"])
        env["_cur_strategy"] = prev


# ── Pore ─────────────────────────────────────────────────────────────────────

class KernelPore:
    """Escalates on out-of-range knobs; most kernel variants are low-risk."""

    _VALID_STRATEGIES = set(KERNELS) | {"tiled"}

    def evaluate(self, candidate: Candidate) -> PoreResult:
        if candidate.type != "kernel":
            return PoreResult(pore="kernel_type", risk_level="high",
                              requires_human_judgment=True, decision="escalate")
        strategy = candidate.params.get("strategy", "naive")
        tile = candidate.params.get("tile_size", 8)
        if strategy not in self._VALID_STRATEGIES:
            return PoreResult(pore="kernel_unknown_strategy", risk_level="high",
                              requires_human_judgment=True, decision="escalate")
        if not (1 <= tile <= _N):
            return PoreResult(pore="kernel_tile_oob", risk_level="medium",
                              requires_human_judgment=True, decision="escalate")
        return PoreResult(pore="kernel_noop", risk_level="low",
                          requires_human_judgment=False, decision="allow")


# ── Test proposer (no Claude API needed) ─────────────────────────────────────

class KernelProposer:
    """Cycles through kernel variants for testing — no Claude API required."""

    _SEQUENCE = [
        {"strategy": "row_order"},
        {"strategy": "comprehension"},
        {"strategy": "tiled", "tile_size": 8},
        {"strategy": "tiled", "tile_size": 4},
        {"strategy": "naive"},
        {"strategy": "comprehension"},
    ]

    def __init__(self):
        self._idx = 0

    def propose(self, task_spec: dict, history: list) -> Candidate:
        params = self._SEQUENCE[self._idx % len(self._SEQUENCE)]
        self._idx += 1
        return Candidate(type="kernel", params=dict(params), reversible=True)
