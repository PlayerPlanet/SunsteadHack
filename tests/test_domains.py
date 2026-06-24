"""End-to-end tests for Epic #8 domain benchmarks.

Each test wires run_loop with a domain's benchmark/actions/pore/proposer and
InMemoryLogClient. No Claude API, no Postgres, no external services.

Run with:
    cd SunsteadHack && PYTHONPATH=. python3 tests/test_domains.py
"""

from cleanroom.fixtures import InMemoryLogClient
from cleanroom.loop import run_loop
from cleanroom.types import Candidate

from cleanroom.domains.kernel import (
    KernelBenchmark, KernelActions, KernelPore, KernelProposer, KERNELS,
)
from cleanroom.domains.quant import (
    QuantBenchmark, QuantActions, QuantPore, QuantProposer, OHLCV_DATA, _N_TRAIN,
)
from cleanroom.domains.bio import (
    BioBenchmark, BioActions, BioPore, BioProposer, BIO_SPLITS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(task_id, env, proposer, benchmark, pore, actions, iterations=7):
    logclient = InMemoryLogClient()
    run_loop(
        task_spec={"task_id": task_id, "model": "test", "conn": env},
        proposer=proposer,
        benchmark=benchmark,
        pore=pore,
        logclient=logclient,
        actions=actions,
        iterations=iterations,
    )
    return logclient.read_experiments()


def _assert_no_incorrect_kept(exps, label):
    for e in exps:
        if e["decision"] == "keep":
            assert e["correctness_ok"], f"{label}: kept an incorrect candidate (id={e['id']})"


# ── Kernel ────────────────────────────────────────────────────────────────────

def test_kernel_e2e():
    env = {"kernel_fn": KERNELS["naive"], "_cur_strategy": "naive"}
    exps = _run("kernel-e2e", env,
                KernelProposer(), KernelBenchmark(), KernelPore(), KernelActions())
    assert exps, "No experiments logged"
    _assert_no_incorrect_kept(exps, "kernel")
    kept = [e for e in exps if e["decision"] == "keep"]
    print(f"  kernel: {len(exps)} experiments, {len(kept)} kept, "
          f"baseline_p99={exps[0]['baseline_p99']:.3f} ms")
    return exps


def test_kernel_correctness_gate():
    """A kernel returning all-zeros is caught by check_correctness and never kept."""
    bench = KernelBenchmark()
    env = {"kernel_fn": lambda A, B: [[0.0] * len(A) for _ in range(len(A))]}
    bad = Candidate(type="kernel", params={"strategy": "wrong"}, reversible=True)
    assert not bench.check_correctness(env, bad), "Wrong kernel should fail correctness"
    print("  kernel correctness gate: PASS")


def test_kernel_pore_bounds():
    """Out-of-range tile size is escalated by the pore."""
    pore = KernelPore()
    bad = Candidate(type="kernel", params={"strategy": "tiled", "tile_size": 999}, reversible=True)
    result = pore.evaluate(bad)
    assert result.requires_human_judgment, "OOB tile should escalate"
    print("  kernel pore bounds: PASS")


# ── Quant ─────────────────────────────────────────────────────────────────────

def test_quant_e2e():
    env = {"lookback": 30, "threshold": 0.02, "data": OHLCV_DATA, "n_train": _N_TRAIN}
    exps = _run("quant-e2e", env,
                QuantProposer(), QuantBenchmark(), QuantPore(), QuantActions())
    assert exps, "No experiments logged"
    _assert_no_incorrect_kept(exps, "quant")
    kept = [e for e in exps if e["decision"] == "keep"]
    print(f"  quant: {len(exps)} experiments, {len(kept)} kept")
    return exps


def test_quant_lookahead_gate():
    """Negative lookback (lookahead strategy) is caught by check_correctness."""
    bench = QuantBenchmark()
    env = {"lookback": -1, "threshold": 0.01, "data": OHLCV_DATA, "n_train": _N_TRAIN}
    bad = Candidate(type="strategy", params={"lookback": -1, "threshold": 0.01}, reversible=True)
    assert not bench.check_correctness(env, bad), "Lookahead should fail"
    print("  quant lookahead gate: PASS")


def test_quant_pore_escalation():
    """Negative lookback is also caught by the pore before apply."""
    pore = QuantPore()
    bad = Candidate(type="strategy", params={"lookback": -5, "threshold": 0.01}, reversible=True)
    result = pore.evaluate(bad)
    assert result.requires_human_judgment
    print("  quant pore escalation: PASS")


# ── Bio ───────────────────────────────────────────────────────────────────────

def test_bio_e2e():
    # Trivial baseline: threshold=0.99 → predicts almost nothing positive → F1≈0
    # Any trained model beats it, producing a clear first descent in the curve.
    env = {"lr": 0.0001, "max_iter": 1, "threshold": 0.99, "l2": 0.0, "splits": BIO_SPLITS}
    exps = _run("bio-e2e", env,
                BioProposer(), BioBenchmark(), BioPore(), BioActions(), iterations=8)
    assert exps, "No experiments logged"
    _assert_no_incorrect_kept(exps, "bio")
    kept = [e for e in exps if e["decision"] == "keep"]
    p99s = [e["candidate_p99"] for e in exps if e["candidate_p99"] is not None]
    print(f"  bio: {len(exps)} experiments, {len(kept)} kept, "
          f"min 1-F1={min(p99s):.3f}" if p99s else f"  bio: {len(exps)} experiments, {len(kept)} kept")
    return exps


def test_bio_leakage_gate():
    """A pipeline that uses test labels is caught by check_correctness."""
    bench = BioBenchmark()
    env = {"lr": 0.01, "max_iter": 100, "threshold": 0.5, "l2": 0.0,
           "splits": BIO_SPLITS, "use_test_labels": True}
    bad = Candidate(type="pipeline",
                    params={"lr": 0.01, "max_iter": 100, "threshold": 0.5, "use_test_labels": True},
                    reversible=True)
    assert not bench.check_correctness(env, bad), "Test-contaminated pipeline should fail"
    print("  bio leakage gate: PASS")


def test_bio_pore_leakage():
    """A candidate requesting test labels is caught by the pore before apply."""
    pore = BioPore()
    bad = Candidate(type="pipeline",
                    params={"lr": 0.01, "max_iter": 100, "threshold": 0.5, "use_test_labels": True},
                    reversible=True)
    result = pore.evaluate(bad)
    assert result.requires_human_judgment
    print("  bio pore leakage: PASS")


# ── Backward-compat: default actions still work ───────────────────────────────

def test_run_loop_default_actions():
    """run_loop with no actions= argument uses cleanroom.actions (Postgres adapter)."""
    from cleanroom.fixtures import CannedBenchmark, NoOpPore, DummyProposer
    logclient = InMemoryLogClient()
    # conn=None triggers the no-op path in cleanroom.actions
    run_loop(
        task_spec={"task_id": "compat-test", "model": "test", "conn": None},
        proposer=DummyProposer(),
        benchmark=CannedBenchmark(baseline_p99=100.0),
        pore=NoOpPore(),
        logclient=logclient,
        iterations=4,
    )
    exps = logclient.read_experiments()
    assert exps, "Backward-compat: should log experiments without injected actions"
    print(f"  backward-compat: {len(exps)} experiments logged")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    tests = [
        ("kernel e2e",               test_kernel_e2e),
        ("kernel correctness gate",  test_kernel_correctness_gate),
        ("kernel pore bounds",       test_kernel_pore_bounds),
        ("quant e2e",                test_quant_e2e),
        ("quant lookahead gate",     test_quant_lookahead_gate),
        ("quant pore escalation",    test_quant_pore_escalation),
        ("bio e2e",                  test_bio_e2e),
        ("bio leakage gate",         test_bio_leakage_gate),
        ("bio pore leakage",         test_bio_pore_leakage),
        ("run_loop backward-compat", test_run_loop_default_actions),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn()
            passed += 1
        except Exception as exc:
            print(f"  FAIL: {exc}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
