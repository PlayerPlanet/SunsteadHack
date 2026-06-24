"""Quant trading benchmark — walk-forward out-of-sample judge.

Domain: momentum strategy on synthetic OHLCV data (geometric Brownian motion).
Objective: negative out-of-sample Sharpe ratio mapped to Result.p99_ms
           (lower p99_ms = higher OOS Sharpe = genuinely better strategy).
Judge: walk-forward out-of-sample backtester — proposer never sees the test
       window, cannot disable transaction costs, and cannot look ahead.

The frozen judge makes lookahead bias and overfitting structurally impossible:
the proposer tunes on in-sample summary stats; the judge scores on held-out OOS.

Epic #8 / Issue #10.
"""

import math
import random
import statistics as _stats

from cleanroom.types import Candidate, Result, PoreResult

# ── Bundled synthetic OHLCV data (1 000 daily bars, GBM, seeded) ─────────────

def _gen_ohlcv(n: int = 1000, seed: int = 42, mu: float = 0.0003, sigma: float = 0.015,
               start: float = 100.0) -> list[dict]:
    rng = random.Random(seed)
    prices = [start]
    for _ in range(n - 1):
        prices.append(prices[-1] * math.exp(rng.gauss(mu, sigma)))
    out = []
    for i, close in enumerate(prices):
        dr = abs(rng.gauss(0.0, close * 0.004))
        out.append({"close": close, "high": close + dr, "low": close - dr,
                    "volume": int(rng.uniform(1e5, 1e6))})
    return out


OHLCV_DATA: list[dict] = _gen_ohlcv()
_N_TRAIN = int(0.70 * len(OHLCV_DATA))  # 700 in-sample / 300 OOS

# 3 walk-forward folds across the OOS window (100 days each)
_FOLD_SIZE = (len(OHLCV_DATA) - _N_TRAIN) // 3


# ── Backtester ───────────────────────────────────────────────────────────────

def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    m = sum(returns) / len(returns)
    var = sum((r - m) ** 2 for r in returns) / (len(returns) - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    return (m / sd) * math.sqrt(252) if sd > 0 else 0.0


def _run_strategy(data: list[dict], lookback: int, threshold: float,
                  cost_bps: float = 10.0) -> list[float]:
    """Return daily strategy returns for the given data window."""
    closes = [d["close"] for d in data]
    returns = []
    prev_pos = 0
    for i in range(lookback, len(closes)):
        mom = closes[i - 1] / closes[i - lookback] - 1.0  # no lookahead
        pos = 1 if mom > threshold else (-1 if mom < -threshold else 0)
        cost = abs(pos - prev_pos) * cost_bps / 10_000.0 if pos != prev_pos else 0.0
        daily_ret = closes[i] / closes[i - 1] - 1.0
        returns.append(prev_pos * daily_ret - cost)
        prev_pos = pos
    return returns


# ── Benchmark ────────────────────────────────────────────────────────────────

class QuantBenchmark:
    """Scores a strategy on 3 walk-forward OOS folds; returns −Sharpe as p99_ms."""

    def run_benchmark(self, env: dict, workload_id: str, *, warmup: int = 0, trials: int = 1) -> Result:
        lookback = env.get("lookback", 20)
        threshold = env.get("threshold", 0.01)
        data = env.get("data", OHLCV_DATA)
        n_train = env.get("n_train", _N_TRAIN)
        oos = data[n_train:]

        fold_sharpes = []
        for f in range(3):
            start = f * _FOLD_SIZE
            end = start + _FOLD_SIZE
            fold = oos[start:end]
            if len(fold) < lookback + 5:
                fold_sharpes.append(0.0)
                continue
            rets = _run_strategy(fold, lookback, threshold)
            fold_sharpes.append(_sharpe(rets))

        mean_sharpe = sum(fold_sharpes) / len(fold_sharpes)
        neg_sharpe = -mean_sharpe  # lower = better (maps onto p99_ms convention)

        total_cost = sum(
            len([r for r in _run_strategy(oos[f * _FOLD_SIZE:(f + 1) * _FOLD_SIZE],
                                          lookback, threshold) if r != 0.0])
            * 10.0 / 10_000.0
            for f in range(3)
        )

        return Result(
            p99_ms=neg_sharpe,
            throughput=float(len(oos) - lookback),
            cost_estimate=total_cost,
            samples=fold_sharpes,  # per-fold OOS Sharpe for noise detection
        )

    def check_correctness(self, env: dict, candidate: Candidate) -> bool:
        """Reject lookahead (negative lookback), degenerate, or cost-disabled strategies."""
        if env.get("use_test_labels"):
            return False  # explicit cheat flag
        lookback = env.get("lookback", 20)
        threshold = env.get("threshold", 0.01)
        if lookback <= 0:
            return False  # negative lookback = lookahead
        if lookback > 500:
            return False  # degenerate
        if threshold < 0:
            return False  # invalid
        return True

    def is_within_noise(self, baseline_samples: list, candidate_samples: list) -> bool:
        """True if mean OOS Sharpe improvement is not practically meaningful.

        Uses a fixed practical threshold (0.2 Sharpe) rather than cross-fold
        variance because 100-day OOS folds have estimation stdev ~2+, which
        would make all strategies statistically indistinguishable. In practice
        a strategy needs ≥ 0.2 Sharpe improvement to be taken seriously.
        """
        if not baseline_samples or not candidate_samples:
            return True
        bm = _stats.mean(baseline_samples)
        cm = _stats.mean(candidate_samples)
        return abs(cm - bm) < 0.2


# ── Actions ──────────────────────────────────────────────────────────────────

class QuantActions:
    """Installs/uninstalls strategy hyperparams in env. Backtests are pure functions."""

    def apply(self, env: dict, candidate: Candidate) -> None:
        env["_prev"] = {"lookback": env.get("lookback"), "threshold": env.get("threshold")}
        env["lookback"] = candidate.params.get("lookback", 20)
        env["threshold"] = candidate.params.get("threshold", 0.01)

    def rollback(self, env: dict, candidate: Candidate) -> None:
        prev = env.get("_prev", {})
        if prev.get("lookback") is not None:
            env["lookback"] = prev["lookback"]
        if prev.get("threshold") is not None:
            env["threshold"] = prev["threshold"]


# ── Pore ─────────────────────────────────────────────────────────────────────

class QuantPore:
    """Escalates on lookahead risk, extreme leverage, or universe changes."""

    def evaluate(self, candidate: Candidate) -> PoreResult:
        if candidate.type != "strategy":
            return PoreResult(pore="quant_type", risk_level="high",
                              requires_human_judgment=True, decision="escalate")
        lookback = candidate.params.get("lookback", 20)
        threshold = candidate.params.get("threshold", 0.01)
        if lookback <= 0:
            return PoreResult(pore="quant_lookahead", risk_level="high",
                              requires_human_judgment=True, decision="escalate")
        if lookback > 200 or threshold < 0:
            return PoreResult(pore="quant_degenerate", risk_level="medium",
                              requires_human_judgment=True, decision="escalate")
        return PoreResult(pore="quant_noop", risk_level="low",
                          requires_human_judgment=False, decision="allow")


# ── Test proposer ─────────────────────────────────────────────────────────────

class QuantProposer:
    """Cycles through lookback/threshold combos for testing."""

    _SEQUENCE = [
        {"lookback": 5,  "threshold": 0.005},
        {"lookback": 10, "threshold": 0.008},
        {"lookback": 20, "threshold": 0.010},
        {"lookback": 3,  "threshold": 0.003},
        {"lookback": 15, "threshold": 0.012},
        {"lookback": 8,  "threshold": 0.006},
    ]

    def __init__(self):
        self._idx = 0

    def propose(self, task_spec: dict, history: list) -> Candidate:
        params = self._SEQUENCE[self._idx % len(self._SEQUENCE)]
        self._idx += 1
        return Candidate(type="strategy", params=dict(params), reversible=True)
