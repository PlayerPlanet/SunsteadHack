"""Computational biology benchmark — held-out truth-set judge.

Domain: molecular property classification (tabular, synthetic, 200 samples, 8 features).
Objective: 1 − F1 on held-out test set, mapped to Result.p99_ms (lower = better accuracy).
Judge: logistic regression trained on train split only; scored against frozen test labels
       the proposer never sees.

The frozen judge makes data leakage and train-on-test structurally impossible:
the proposer tunes pipeline hyperparams; the judge fits on train and scores on
the sealed test set. The test split is never passed to apply().

Epic #8 / Issue #11.
"""

import math
import random
import statistics as _stats

from cleanroom.types import Candidate, Result, PoreResult

# ── Bundled synthetic dataset (200 samples, 8 features, seeded) ──────────────

def _gen_bio_data(n: int = 200, n_features: int = 8, seed: int = 42):
    """Synthetic molecular property classification dataset.

    True signal: linear combination of first 3 features + Gaussian noise.
    """
    rng = random.Random(seed)
    X = [[rng.gauss(0.0, 1.0) for _ in range(n_features)] for _ in range(n)]
    true_w = [1.5, -1.0, 0.8] + [0.0] * (n_features - 3)
    y = []
    for xi in X:
        score = sum(w * x for w, x in zip(true_w, xi)) + rng.gauss(0.0, 0.6)
        y.append(1 if score > 0 else 0)
    return X, y


def _split(X, y, train_frac=0.60, dev_frac=0.20):
    n = len(X)
    n_train = int(train_frac * n)
    n_dev = int(dev_frac * n)
    return (
        X[:n_train], y[:n_train],
        X[n_train:n_train + n_dev], y[n_train:n_train + n_dev],
        X[n_train + n_dev:], y[n_train + n_dev:],
    )


_X, _y = _gen_bio_data()
_X_train, _y_train, _X_dev, _y_dev, _X_test, _y_test = _split(_X, _y)

BIO_SPLITS = {
    "X_train": _X_train, "y_train": _y_train,
    "X_dev": _X_dev,   "y_dev": _y_dev,
    "X_test": _X_test,  "y_test": _y_test,  # SEALED — never exposed to proposer
}


# ── Logistic regression (pure Python, no deps) ───────────────────────────────

def _sigmoid(x: float) -> float:
    if x > 500:
        return 1.0
    if x < -500:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _train(X_train, y_train, *, lr: float, max_iter: int, l2: float) -> tuple:
    n_feat = len(X_train[0])
    w = [0.0] * n_feat
    b = 0.0
    for _ in range(max_iter):
        for xi, yi in zip(X_train, y_train):
            score = sum(wj * xj for wj, xj in zip(w, xi)) + b
            pred = _sigmoid(score)
            err = pred - yi
            w = [wj - lr * (err * xi[j] + l2 * wj) for j, wj in enumerate(w)]
            b -= lr * err
    return w, b


def _predict(X, w, b, threshold: float) -> list[int]:
    return [1 if _sigmoid(sum(wj * xj for wj, xj in zip(w, xi)) + b) >= threshold else 0
            for xi in X]


def _f1(y_true: list, y_pred: list) -> float:
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


# ── Benchmark ────────────────────────────────────────────────────────────────

class BioBenchmark:
    """Trains on X_train, scores on sealed X_test. Returns 1−F1 as p99_ms."""

    def run_benchmark(self, env: dict, workload_id: str, *, warmup: int = 0, trials: int = 1) -> Result:
        splits = env.get("splits", BIO_SPLITS)
        lr = env.get("lr", 0.01)
        max_iter = env.get("max_iter", 100)
        threshold = env.get("threshold", 0.5)
        l2 = env.get("l2", 0.0)

        w, b = _train(splits["X_train"], splits["y_train"],
                      lr=lr, max_iter=max_iter, l2=l2)

        # Score on two held-out shards for noise detection
        X_test = splits["X_test"]
        y_test = splits["y_test"]
        mid = len(X_test) // 2
        shard_f1s = []
        for xs, ys in [(X_test[:mid], y_test[:mid]), (X_test[mid:], y_test[mid:])]:
            if len(xs) == 0:
                continue
            preds = _predict(xs, w, b, threshold)
            shard_f1s.append(_f1(ys, preds))

        mean_f1 = sum(shard_f1s) / len(shard_f1s) if shard_f1s else 0.0
        loss = 1.0 - mean_f1  # lower = better

        return Result(
            p99_ms=loss,
            throughput=float(len(X_test)),
            cost_estimate=0.0,
            samples=shard_f1s,  # per-shard F1 for is_within_noise
        )

    def check_correctness(self, env: dict, candidate: Candidate) -> bool:
        """Reject any pipeline that touches test labels or has invalid params."""
        if env.get("use_test_labels"):
            return False  # explicit contamination flag
        if candidate.params.get("use_test_labels"):
            return False
        lr = env.get("lr", 0.01)
        max_iter = env.get("max_iter", 100)
        threshold = env.get("threshold", 0.5)
        if lr <= 0 or max_iter <= 0:
            return False
        if not (0.0 < threshold < 1.0):
            return False
        return True

    def is_within_noise(self, baseline_samples: list, candidate_samples: list) -> bool:
        """True if mean F1 improvement across shards is smaller than cross-shard variation."""
        if not baseline_samples or not candidate_samples:
            return True
        bm = _stats.mean(baseline_samples)
        cm = _stats.mean(candidate_samples)
        if len(baseline_samples) > 1 and len(candidate_samples) > 1:
            bstd = _stats.stdev(baseline_samples)
            cstd = _stats.stdev(candidate_samples)
            combined = (bstd + cstd) / 2.0 or 0.03
            return abs(cm - bm) < combined
        return abs(cm - bm) < 0.03


# ── Actions ──────────────────────────────────────────────────────────────────

class BioActions:
    """Installs/uninstalls pipeline hyperparams in env. Fits are pure functions of train data."""

    def apply(self, env: dict, candidate: Candidate) -> None:
        env["_prev"] = {k: env.get(k) for k in ("lr", "max_iter", "threshold", "l2", "use_test_labels")}
        for key in ("lr", "max_iter", "threshold", "l2", "use_test_labels"):
            if key in candidate.params:
                env[key] = candidate.params[key]

    def rollback(self, env: dict, candidate: Candidate) -> None:
        for key, val in env.get("_prev", {}).items():
            if val is not None:
                env[key] = val
            elif key in env:
                del env[key]


# ── Pore ─────────────────────────────────────────────────────────────────────

class BioPore:
    """Escalates on split-definition changes and obviously invalid params."""

    def evaluate(self, candidate: Candidate) -> PoreResult:
        if candidate.type != "pipeline":
            return PoreResult(pore="bio_type", risk_level="high",
                              requires_human_judgment=True, decision="escalate")
        if candidate.params.get("use_test_labels"):
            return PoreResult(pore="bio_leakage", risk_level="high",
                              requires_human_judgment=True, decision="escalate")
        lr = candidate.params.get("lr", 0.01)
        max_iter = candidate.params.get("max_iter", 100)
        threshold = candidate.params.get("threshold", 0.5)
        if lr <= 0 or lr > 100 or max_iter <= 0 or max_iter > 50_000:
            return PoreResult(pore="bio_invalid_params", risk_level="medium",
                              requires_human_judgment=True, decision="escalate")
        if not (0.0 < threshold < 1.0):
            return PoreResult(pore="bio_invalid_threshold", risk_level="medium",
                              requires_human_judgment=True, decision="escalate")
        return PoreResult(pore="bio_noop", risk_level="low",
                          requires_human_judgment=False, decision="allow")


# ── Test proposer ─────────────────────────────────────────────────────────────

class BioProposer:
    """Cycles through LR hyperparams for testing — starts poor, improves progressively."""

    _SEQUENCE = [
        {"lr": 0.001,  "max_iter": 10,  "threshold": 0.5,  "l2": 0.0},   # very poor baseline
        {"lr": 0.05,   "max_iter": 200, "threshold": 0.45, "l2": 0.01},   # much better
        {"lr": 0.1,    "max_iter": 300, "threshold": 0.4,  "l2": 0.01},   # further tuning
        {"lr": 0.02,   "max_iter": 200, "threshold": 0.5,  "l2": 0.0},    # regularization test
        {"lr": 0.05,   "max_iter": 500, "threshold": 0.45, "l2": 0.001},  # more iters
        {"lr": 0.08,   "max_iter": 300, "threshold": 0.4,  "l2": 0.005},  # tuned
        {"lr": 0.05,   "max_iter": 200, "threshold": 0.35, "l2": 0.01},   # threshold search
    ]

    def __init__(self):
        self._idx = 0

    def propose(self, task_spec: dict, history: list) -> Candidate:
        params = self._SEQUENCE[self._idx % len(self._SEQUENCE)]
        self._idx += 1
        return Candidate(type="pipeline", params=dict(params), reversible=True)
