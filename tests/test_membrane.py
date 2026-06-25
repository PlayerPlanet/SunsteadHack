"""Issue #20: the shadow membrane gate, its abstain head, and the frozen ruler.

Proves the four load-bearing properties:
  1. The abstain head fires on unseen / mixed / thin-support levers (the calibration
     target: err toward asking), and auto_clear/escalate fire on clean precedent.
  2. False-clears are structurally impossible in the full-fit deployment gate — a
     lever with any reject in its record is never auto-cleared.
  3. ShadowMembranePore never touches the wheel: run_loop's real decision is the
     frozen base pore's, byte-for-byte, while the membrane decision is only recorded.
  4. The frozen pore (cleanroom/pore/__init__.py) is byte-for-byte unchanged — both
     by file hash and by decision-equivalence through the wrapper.

Run with:
    cd SunsteadHack && PYTHONPATH=. python3 tests/test_membrane.py
"""

import hashlib
from pathlib import Path

import cleanroom.pore as base_pore
from cleanroom.fixtures import CannedBenchmark, InMemoryLogClient
from cleanroom.membrane import Membrane, MembraneDecision, ShadowMembranePore, lever_of
from cleanroom.types import Candidate

# Pinned hash of the FROZEN base pore. The pore is frozen by contract (see its module
# docstring and cleanroom/types.py): editing it requires co-author sign-off AND a
# deliberate update of this pin. Issue #20's membrane must NOT move this ruler.
# NOTE: this is the LF (canonical git-blob) hash. The original pin (ae0ab3b2...) was the
# CRLF rendering — it was computed on a Windows checkout where autocrlf turned the LF
# blob into CRLF on disk, so the test passed locally but failed on Linux CI (which reads
# LF). The pore content never changed. .gitattributes now pins this file to eol=lf so the
# on-disk bytes are deterministic across platforms and this hash holds everywhere.
FROZEN_PORE_SHA256 = "aaeb71904ef3d88ce6d798be83810ab4376f14d9267440ebef045295c503e540"


def _guc(name: str, reversible: bool = True) -> Candidate:
    return Candidate(type="guc", params={"name": name}, reversible=reversible)


# --- 1. the three-outcome gate + abstain head -------------------------------

def test_abstain_head_and_decisions():
    # A membrane with a clean-approve lever, a clean-reject lever, a mixed lever.
    m = Membrane.from_counts({
        "shared_buffers": {"approve": 2, "reject": 0},     # clean approve
        "fsync": {"approve": 0, "reject": 3},              # clean reject
        "synchronous_commit": {"approve": 4, "reject": 1}, # mixed -> irreducible
    })

    assert m.evaluate(_guc("shared_buffers")).decision == "auto_clear"
    assert m.evaluate(_guc("fsync")).decision == "escalate"
    # Mixed verdict: the abstain head fires (err toward asking).
    assert m.evaluate(_guc("synchronous_commit")).decision == "abstain"
    # Unseen lever: no precedent -> abstain, flagged not-seen.
    unseen = m.evaluate(_guc("max_parallel_workers"))
    assert unseen.decision == "abstain" and unseen.seen is False
    # Thin support: a single approve is not enough to stand behind -> abstain.
    thin = Membrane.from_counts({"work_mem": {"approve": 1, "reject": 0}})
    assert thin.evaluate(_guc("work_mem")).decision == "abstain"
    print("  abstain head + auto_clear/escalate decisions: PASS")


def test_calibrated_probability_monotone():
    m = Membrane.from_counts({
        "fsync": {"approve": 0, "reject": 3},
        "synchronous_commit": {"approve": 4, "reject": 1},
        "shared_buffers": {"approve": 2, "reject": 0},
    })
    p_reject = m.evaluate(_guc("fsync")).p_approve
    p_mixed = m.evaluate(_guc("synchronous_commit")).p_approve
    p_clear = m.evaluate(_guc("shared_buffers")).p_approve
    # The score is a probability and orders reject < mixed < clear.
    assert 0.0 <= p_reject < p_mixed < p_clear <= 1.0
    print(f"  calibrated p_approve orders reject<{p_reject:.2f} mixed<{p_mixed:.2f} clear<{p_clear:.2f}: PASS")


def test_irreversible_never_auto_cleared():
    # Even a spotless approve record cannot auto-clear an irreversible candidate.
    m = Membrane.from_counts({"vacuum_full": {"approve": 9, "reject": 0}})
    d = m.evaluate(Candidate(type="maintenance", params={"op": "vacuum_full"}, reversible=False))
    assert d.decision == "abstain" and "irreversible" in d.reason
    print("  irreversible defense-in-depth (never auto_clear): PASS")


# --- 2. false-clears are structurally impossible in the full-fit gate -------

def test_no_false_clear_on_any_reject_lever():
    # Construct levers that each carry at least one reject; none may auto_clear.
    m = Membrane.from_counts({
        "a": {"approve": 10, "reject": 1},
        "b": {"approve": 1, "reject": 1},
        "c": {"approve": 0, "reject": 5},
    })
    for lv in ("a", "b", "c"):
        assert m.evaluate(_guc(lv)).decision != "auto_clear", f"{lv} false-cleared"
    print("  no lever with a reject is ever auto-cleared (false-clear floor): PASS")


# --- 3. shadow wiring through run_loop --------------------------------------

class _CountingActions:
    """Records apply/rollback so the test can prove the membrane never acts."""

    def __init__(self):
        self.applies = 0
        self.rollbacks = 0

    def apply(self, conn, candidate):
        self.applies += 1

    def rollback(self, conn, candidate):
        self.rollbacks += 1


class _AlwaysEscalatesProposer:
    """Proposes a high-blast GUC every step so the FROZEN base pore always escalates."""

    def propose(self, task_spec, history):
        return _guc("shared_buffers")  # high-blast-radius -> base pore escalates


def test_shadow_pore_never_acts_and_logs_membrane():
    from cleanroom import loop

    membrane = Membrane.from_counts({"shared_buffers": {"approve": 2, "reject": 0}})
    shadow = ShadowMembranePore(membrane=membrane, drift_level=0.9)
    logclient = InMemoryLogClient()
    actions = _CountingActions()

    loop.run_loop(
        {"task_id": "shadow-test", "workload_id": "wl", "conn": {}},
        proposer=_AlwaysEscalatesProposer(),
        benchmark=CannedBenchmark(),
        pore=shadow,
        logclient=logclient,
        actions=actions,
        iterations=6,
    )

    exps = logclient.read_experiments()
    assert exps, "no experiments logged"
    # The REAL decision run_loop acted on is the frozen base pore's: escalated.
    assert all(e["decision"] == "escalated" for e in exps), \
        f"base pore decision changed: {[e['decision'] for e in exps]}"
    # The membrane never got the wheel: an escalation skips apply, so apply==0.
    assert actions.applies == 0, f"membrane caused {actions.applies} applies — it acted!"
    # ...but every escalation carries the membrane's shadow decision.
    assert shadow.shadow_log, "membrane shadow decision was not recorded"
    assert all(s["base_decision"] == "escalate" for s in shadow.shadow_log)
    assert all(s["membrane_decision"] == "auto_clear" for s in shadow.shadow_log), \
        "membrane should have shadow-cleared the clean-precedent lever"
    print(f"  shadow pore: {len(exps)} escalations, 0 applies, "
          f"{len(shadow.shadow_log)} membrane shadow decisions logged: PASS")


def test_shadow_decision_equals_base_decision():
    # For a battery of candidates the wrapper's REAL output must equal the base pore's
    # — the membrane is shadow-only and cannot alter what run_loop acts on.
    membrane = Membrane.from_counts({"shared_buffers": {"approve": 2, "reject": 0}})
    shadow = ShadowMembranePore(membrane=membrane, drift_level=0.5)
    cands = [
        _guc("shared_buffers"),
        _guc("fsync"),
        Candidate(type="index", params={"table": "title", "columns": ["x"]}, reversible=True),
        Candidate(type="maintenance", params={"op": "vacuum_full"}, reversible=False),
        Candidate(type="guc", params={"name": "work_mem"}, reversible=True),
    ]
    for c in cands:
        assert shadow.evaluate(c) == base_pore.evaluate(c), f"wrapper altered base decision for {c}"
    print("  wrapper decision == frozen base pore decision for all candidates: PASS")


# --- 4. the frozen ruler did not move ---------------------------------------

def test_frozen_pore_byte_for_byte_unchanged():
    src = Path(__file__).resolve().parent.parent / "cleanroom" / "pore" / "__init__.py"
    actual = hashlib.sha256(src.read_bytes()).hexdigest()
    assert actual == FROZEN_PORE_SHA256, (
        f"cleanroom/pore/__init__.py changed!\n  expected {FROZEN_PORE_SHA256}\n  actual   {actual}\n"
        "The membrane must NOT move the frozen ruler. If this edit is intentional and "
        "signed off, update FROZEN_PORE_SHA256 deliberately."
    )
    print("  frozen pore byte-for-byte unchanged (sha256 pinned): PASS")


# --- 5. data-driven: deployment gate has zero false-clears (if dataset present) ---

def test_deployment_zero_false_clears_on_real_data():
    ds = Path(__file__).resolve().parent.parent / "artifacts" / "deep_probe" / "dataset.jsonl"
    if not ds.exists():
        print("  (skipped — no probe dataset on disk)")
        return
    import json

    rows = [json.loads(l) for l in ds.read_text(encoding="utf-8").splitlines() if l.strip()]
    esc = [r for r in rows if r.get("escalated") and r.get("human_decision") in ("approve", "reject")]
    m = Membrane.from_records(rows)
    false_clears, reclaimed, abstains = 0, 0, []
    for r in esc:
        c = r["candidate"]
        d = m.evaluate(Candidate(type=c["type"], params=c.get("params") or {}, reversible=c["reversible"]),
                       {"drift": r["drift"]})
        if d.decision == "auto_clear":
            if r["human_decision"] == "reject":
                false_clears += 1
            else:
                reclaimed += 1
        elif d.decision == "abstain":
            abstains.append(lever_of(Candidate(type=c["type"], params=c.get("params") or {}, reversible=c["reversible"])))
    assert false_clears == 0, f"{false_clears} false-clears on real data — the dangerous error"
    assert reclaimed > 0, "membrane reclaimed no false stops — no bend"
    # Abstention concentrates on the irreducible mixed lever.
    assert set(abstains) <= {"synchronous_commit"}, f"abstained on unexpected levers: {set(abstains)}"
    print(f"  real data: 0 false-clears, {reclaimed} reclaimed, abstains only on synchronous_commit: PASS")


if __name__ == "__main__":
    import sys

    tests = [
        ("abstain head + decisions", test_abstain_head_and_decisions),
        ("calibrated probability", test_calibrated_probability_monotone),
        ("irreversible never cleared", test_irreversible_never_auto_cleared),
        ("no false-clear floor", test_no_false_clear_on_any_reject_lever),
        ("shadow never acts", test_shadow_pore_never_acts_and_logs_membrane),
        ("wrapper==base decision", test_shadow_decision_equals_base_decision),
        ("frozen pore unchanged", test_frozen_pore_byte_for_byte_unchanged),
        ("deployment zero false-clears", test_deployment_zero_false_clears_on_real_data),
    ]
    passed = failed = 0
    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            failed += 1
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
