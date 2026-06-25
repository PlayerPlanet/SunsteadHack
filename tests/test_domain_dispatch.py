"""Epic #8 DoD: domain TaskSpecs dispatch through Story D's control plane unchanged.

Where tests/test_domains.py wires run_loop directly, this proves the *control-plane*
path: each committed domain task (kernel/quant/bio) is dispatched via the Operator
— the same fire-and-return dispatch_run the MCP server and CLI call — runs the
domain judge on a background thread, writes experiments to the governance log, and
produces a descending loss curve. No Postgres, no Claude API.

The injected ctx deliberately carries the WRONG components (DummyProposer +
CannedBenchmark, which would never descend): if the curve still descends, the
domain binding in Operator.dispatch_run correctly overrode them.

Run with:
    cd SunsteadHack && PYTHONPATH=. python3 tests/test_domain_dispatch.py
"""

import time

import cleanroom.pore
from cleanroom.control.dispatcher.store_interface import InMemoryRunStore
from cleanroom.control.ops import Operator, OperatorContext
from cleanroom.control.registry.store import TaskRegistryStore
from cleanroom.fixtures import CannedBenchmark, DummyProposer, InMemoryLogClient

TASKS_DIR = "cleanroom/control/tasks"


def _wait(op: Operator, run_id: str, timeout: float = 30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = op.get_run(run_id)
        if st and st.state in ("done", "failed", "cancelled"):
            return st
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not finish within {timeout}s")


def _dispatch(task_id: str, iterations: int = 8):
    logclient = InMemoryLogClient()
    op = Operator(TaskRegistryStore(TASKS_DIR), InMemoryRunStore())
    assert op.get_task(task_id) is not None, f"{task_id} not registered in {TASKS_DIR}"
    # Intentionally-wrong ctx: dispatch_run must override it for a domain task.
    ctx = OperatorContext(
        proposer=DummyProposer(),
        benchmark=CannedBenchmark(),
        pore=cleanroom.pore,
        logclient=logclient,
    )
    run_id = op.dispatch_run(task_id, model="test", iterations=iterations, ctx=ctx)
    st = _wait(op, run_id)
    assert st.state == "done", f"{task_id}: state={st.state} error={st.error_msg}"
    return op, run_id, logclient.read_experiments()


def _assert_descending_and_clean(task_id: str, exps: list, op: Operator, run_id: str):
    assert exps, f"{task_id}: no experiments written to the log"

    # No incorrect candidate was ever kept (the frozen judge held).
    for e in exps:
        if e["decision"] == "keep":
            assert e["correctness_ok"], f"{task_id}: kept an incorrect candidate (id={e['id']})"

    baseline0 = exps[0]["baseline_p99"]
    kept = [e for e in exps if e["decision"] == "keep" and e["candidate_p99"] is not None]
    assert kept, f"{task_id}: no candidate was kept — the loop never made progress"

    # Descending curve: each successive keep is a real improvement, so the kept
    # candidate_p99 series is monotonically non-increasing. (run_loop only keeps a
    # candidate that beats the standing baseline outside noise, so this is the
    # descent invariant — independent of whether the very first iteration kept,
    # which would otherwise hide the pre-improvement baseline from the log.)
    kept_losses = [e["candidate_p99"] for e in kept]
    assert all(b >= a for b, a in zip(kept_losses, kept_losses[1:])), (
        f"{task_id}: kept curve is not non-increasing: {kept_losses}"
    )
    best = min(kept_losses)
    assert best <= baseline0, f"{task_id}: best kept {best:.4f} above first baseline {baseline0:.4f}"

    # The control plane's progress tap tracked the same run on its background thread.
    # The tap minimizes over every evaluated candidate (not just keeps), so it is at
    # least as good as the best kept loss.
    st = op.get_run(run_id)
    assert st.best_p99 is not None and st.iterations_done > 0
    assert st.best_p99 <= best + 1e-9, (
        f"{task_id}: run_store best_p99 {st.best_p99} worse than log best {best}"
    )
    print(
        f"  {task_id}: {len(exps)} exps, {len(kept)} kept, "
        f"first_baseline={baseline0:.4f} -> best={best:.4f}  [dispatched via Operator]"
    )


def test_kernel_dispatch():
    op, run_id, exps = _dispatch("kernel-matmul")
    _assert_descending_and_clean("kernel-matmul", exps, op, run_id)


def test_quant_dispatch():
    op, run_id, exps = _dispatch("quant-walkforward")
    _assert_descending_and_clean("quant-walkforward", exps, op, run_id)


def test_bio_dispatch():
    op, run_id, exps = _dispatch("bio-molclass")
    _assert_descending_and_clean("bio-molclass", exps, op, run_id)


def test_postgres_task_unaffected():
    """A non-domain workload_id resolves to None -> ctx + builtin actions untouched."""
    from cleanroom.control.domains import resolve_domain

    assert resolve_domain({"workload_id": "tpch_q5"}) is None
    assert resolve_domain({"workload_id": "kernel_matmul_32"}) is not None
    print("  postgres/unknown workload -> default dispatch path: PASS")


if __name__ == "__main__":
    import sys

    tests = [
        ("kernel dispatch", test_kernel_dispatch),
        ("quant dispatch", test_quant_dispatch),
        ("bio dispatch", test_bio_dispatch),
        ("postgres unaffected", test_postgres_task_unaffected),
    ]
    passed = failed = 0
    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL: {exc}")
            failed += 1
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
