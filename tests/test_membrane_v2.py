"""Membrane v2: semantic-risk generalization, decision theory, OOD abstention.

The headline claim v2 makes that v1 cannot: on a lever it has NEVER seen, v2 still
makes the right call by generalizing from the lever's risk profile. These tests pin
that, plus the decision-theoretic frontier monotonicity, the OOD abstain head, the
shadow-only discipline (reusing v1's ShadowMembranePore), and the frozen ruler.

Run with:
    cd SunsteadHack && PYTHONPATH=. python3 tests/test_membrane_v2.py
"""

import hashlib
import json
from pathlib import Path

import cleanroom.pore as base_pore
from cleanroom.fixtures import CannedBenchmark, InMemoryLogClient
from cleanroom.membrane import Membrane, ShadowMembranePore  # v1 pieces reused
from cleanroom.membrane.taxonomy import (
    DATA_LOSS_BOUNDED,
    DATA_LOSS_HIGH,
    DATA_LOSS_NONE,
    feature_vector,
)
from cleanroom.membrane.v2 import MembraneV2
from cleanroom.types import Candidate

FROZEN_PORE_SHA256 = "ae0ab3b284cee68d378db4f8190bfb952827310c562f1b4aab0b74d6952ec6fd"
DATASET = Path(__file__).resolve().parent.parent / "artifacts" / "deep_probe" / "dataset.jsonl"


def _guc(name, reversible=True):
    return Candidate(type="guc", params={"name": name}, reversible=reversible)


def _rows():
    return [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines() if l.strip()]


# --- taxonomy ---------------------------------------------------------------

def test_taxonomy_features():
    assert feature_vector(_guc("fsync"))["data_loss_on_crash"] == DATA_LOSS_HIGH
    assert feature_vector(_guc("full_page_writes"))["data_loss_on_crash"] == DATA_LOSS_HIGH
    assert feature_vector(_guc("synchronous_commit"))["data_loss_on_crash"] == DATA_LOSS_BOUNDED
    assert feature_vector(_guc("shared_buffers"))["data_loss_on_crash"] == DATA_LOSS_NONE
    assert feature_vector(_guc("max_wal_size"))["data_loss_on_crash"] == DATA_LOSS_NONE
    print("  taxonomy maps levers to documented data-loss risk: PASS")


# --- the headline: cross-lever generalization on held-out levers ------------

def test_lolo_generalizes_where_v1_abstains():
    if not DATASET.exists():
        print("  (skipped — no dataset)"); return
    rows = _rows()
    fsync = next(r for r in rows if (r["candidate"]["params"].get("name") == "fsync"
                                     and r.get("escalated") and r.get("human_decision")))
    # Hold out fsync ENTIRELY. v2 has never seen it.
    v2 = MembraneV2.from_records(rows, exclude_lever="fsync")
    v1 = Membrane.from_records(rows, exclude_lever="fsync")
    c = Candidate(type="guc", params={"name": "fsync"}, reversible=True)

    # v2 generalizes from full_page_writes (data_loss=HIGH -> reject) and escalates COLD.
    assert v2.evaluate(c).decision == "escalate", "v2 failed to generalize the reject"
    # v1 has no precedent for the *name* and can only abstain.
    assert v1.evaluate(c).decision == "abstain", "v1 unexpectedly committed"
    print("  held-out fsync: v2 escalates cold, v1 abstains — generalization: PASS")


def test_lolo_reclaims_sizing_knob_cold():
    if not DATASET.exists():
        print("  (skipped — no dataset)"); return
    rows = _rows()
    # Hold out shared_buffers entirely; v2 should still auto_clear it, generalizing
    # from max_wal_size (also data_loss=NONE, recoverable sizing).
    v2 = MembraneV2.from_records(rows, exclude_lever="shared_buffers")
    d = v2.evaluate(_guc("shared_buffers"))
    assert d.decision == "auto_clear", f"expected cold auto_clear, got {d.decision} ({d.reason})"
    print("  held-out shared_buffers: v2 auto_clears cold from a sizing peer: PASS")


def test_lolo_no_false_clears_overall():
    if not DATASET.exists():
        print("  (skipped — no dataset)"); return
    rows = _rows()
    esc = [r for r in rows if r.get("escalated") and r.get("human_decision") in ("approve", "reject")]
    levers = {r["candidate"]["params"].get("name") or r["candidate"]["params"].get("op")
              or r["candidate"]["type"] for r in esc}
    fc = 0
    for lv in levers:
        m = MembraneV2.from_records(rows, exclude_lever=lv)
        for r in [r for r in esc if (r["candidate"]["params"].get("name")
                  or r["candidate"]["params"].get("op") or r["candidate"]["type"]) == lv]:
            c = r["candidate"]
            d = m.evaluate(Candidate(type=c["type"], params=c.get("params") or {}, reversible=c["reversible"]))
            if d.decision == "auto_clear" and r["human_decision"] == "reject":
                fc += 1
    assert fc == 0, f"{fc} held-out false-clears — the dangerous error"
    print("  leave-one-lever-out: zero false-clears across all held-out levers: PASS")


# --- OOD abstain head -------------------------------------------------------

def test_ood_abstains():
    if not DATASET.exists():
        print("  (skipped — no dataset)"); return
    m = MembraneV2.from_records(_rows())
    # A rewrite that changes result semantics: a class never adjudicated -> abstain.
    rew = m.evaluate(Candidate(type="rewrite", params={"op": "query_rewrite"}, reversible=True))
    assert rew.decision == "abstain" and rew.ood
    # An unrecognised systemic lever -> abstain (refuse to assume it is safe).
    unk = m.evaluate(_guc("some_unmapped_guc"))
    assert unk.decision == "abstain" and unk.ood
    # An irreversible op is never auto-cleared.
    irr = m.evaluate(Candidate(type="maintenance", params={"op": "vacuum_full"}, reversible=False))
    assert irr.decision != "auto_clear"
    print("  OOD head abstains on novel-semantics / unknown / irreversible: PASS")


# --- decision theory: the frontier is monotone ------------------------------

def test_frontier_monotone_in_rho():
    if not DATASET.exists():
        print("  (skipped — no dataset)"); return
    rows = _rows()
    esc = [r for r in rows if r.get("escalated") and r.get("human_decision") in ("approve", "reject")]

    def cleared_and_fc(rho):
        m = MembraneV2.from_records(rows, rho=rho)
        cleared = fc = 0
        for r in esc:
            c = r["candidate"]
            d = m.evaluate(Candidate(type=c["type"], params=c.get("params") or {}, reversible=c["reversible"]))
            if d.decision == "auto_clear":
                cleared += 1
                fc += 1 if r["human_decision"] == "reject" else 0
        return cleared, fc

    seq = [cleared_and_fc(r) for r in (0.05, 0.15, 0.25, 0.35, 0.5, 0.9)]
    clears = [c for c, _ in seq]
    fcs = [f for _, f in seq]
    # Raising rho (tolerating more false-clear risk) only ever clears more, never fewer.
    assert clears == sorted(clears), f"cleared not monotone in rho: {clears}"
    assert fcs == sorted(fcs), f"false-clears not monotone in rho: {fcs}"
    # The conservative end (rho<=0.25) has zero false-clears — v1's knee.
    assert cleared_and_fc(0.25)[1] == 0
    print(f"  frontier monotone in rho (clears={clears}, fc={fcs}); zero-fc knee at rho<=0.25: PASS")


# --- shadow discipline (reuse v1 ShadowMembranePore with a v2 membrane) -----

class _AlwaysEscalatesProposer:
    def propose(self, task_spec, history):
        return _guc("shared_buffers")  # high-blast -> frozen base pore escalates


class _CountingActions:
    def __init__(self): self.applies = 0
    def apply(self, conn, candidate): self.applies += 1
    def rollback(self, conn, candidate): pass


def test_v2_shadow_never_acts():
    if not DATASET.exists():
        print("  (skipped — no dataset)"); return
    from cleanroom import loop

    v2 = MembraneV2.from_records(_rows())
    shadow = ShadowMembranePore(membrane=v2, drift_level=0.9)  # v1 wrapper, v2 brain
    logclient = InMemoryLogClient()
    actions = _CountingActions()
    loop.run_loop(
        {"task_id": "v2-shadow", "workload_id": "wl", "conn": {}},
        proposer=_AlwaysEscalatesProposer(), benchmark=CannedBenchmark(),
        pore=shadow, logclient=logclient, actions=actions, iterations=5,
    )
    exps = logclient.read_experiments()
    assert exps and all(e["decision"] == "escalated" for e in exps), "base decision changed"
    assert actions.applies == 0, "membrane v2 caused an apply — it acted!"
    assert shadow.shadow_log and all(s["membrane_decision"] == "auto_clear" for s in shadow.shadow_log)
    print(f"  v2 shadow: {len(exps)} escalations, 0 applies, v2 decisions logged: PASS")


def test_frozen_pore_unchanged():
    src = Path(__file__).resolve().parent.parent / "cleanroom" / "pore" / "__init__.py"
    assert hashlib.sha256(src.read_bytes()).hexdigest() == FROZEN_PORE_SHA256, \
        "frozen pore changed — v2 must not move the ruler"
    print("  frozen pore byte-for-byte unchanged: PASS")


if __name__ == "__main__":
    import sys

    tests = [
        ("taxonomy features", test_taxonomy_features),
        ("LOLO generalizes (v2 vs v1)", test_lolo_generalizes_where_v1_abstains),
        ("LOLO reclaims sizing cold", test_lolo_reclaims_sizing_knob_cold),
        ("LOLO zero false-clears", test_lolo_no_false_clears_overall),
        ("OOD abstains", test_ood_abstains),
        ("frontier monotone", test_frontier_monotone_in_rho),
        ("v2 shadow never acts", test_v2_shadow_never_acts),
        ("frozen pore unchanged", test_frozen_pore_unchanged),
    ]
    passed = failed = 0
    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn(); passed += 1
        except Exception as exc:  # noqa: BLE001
            import traceback; traceback.print_exc(); failed += 1
    print(f"\n{'=' * 50}\nResults: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
