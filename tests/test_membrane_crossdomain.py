"""Cross-domain membrane probe (issue #20 follow-on).

Pins the two honestly-testable cross-domain properties:

  A. The POSTGRES-trained membrane, shown REAL kernel/quant/bio candidates, abstains
     on every one (recognises them as out-of-taxonomy) instead of transferring a
     spurious Postgres verdict. The "knows its edge" property holds at the domain
     boundary — zero reckless cross-domain auto_clears/escalates.

  B. The decision machinery is domain-agnostic: with a per-domain risk prior on the
     abstract "violates a correctness invariant?" axis, the same 3-outcome gate matches
     each domain's OWN frozen judge (escalate the violation, clear the safe tuning).

True *predictive* transfer (train on Postgres labels, predict a foreign human verdict)
is NOT tested here — there are no held-out-domain governance labels. That needs a probe
per domain, and is the next issue.

Run with:
    cd SunsteadHack && PYTHONPATH=. python3 tests/test_membrane_crossdomain.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from cleanroom.control.domains import resolve_domain  # noqa: E402
from cleanroom.membrane.v2 import MembraneV2  # noqa: E402
from eval_membrane_crossdomain import (  # noqa: E402
    DOMAINS,
    _domain_rejects,
    _violation,
    portable_gate,
)

DATASET = ROOT / "artifacts" / "deep_probe" / "dataset.jsonl"


def test_postgres_membrane_abstains_on_all_foreign_domains():
    if not DATASET.exists():
        print("  (skipped — no dataset)"); return
    pg = MembraneV2.from_dataset(str(DATASET))
    for domain, wl in DOMAINS.items():
        bundle = resolve_domain({"workload_id": wl})
        for kind, cand in (("safe", bundle.proposer.propose({"workload_id": wl}, [])),
                           ("violation", _violation(domain))):
            d = pg.evaluate(cand)
            assert d.decision == "abstain" and d.ood, (
                f"{domain}/{kind}: Postgres membrane did not abstain on a foreign-domain "
                f"candidate (got {d.decision}, ood={d.ood}) — reckless cross-domain transfer"
            )
    print("  Postgres membrane abstains (OOD) on all kernel/quant/bio candidates: PASS")


def test_portable_gate_matches_each_domains_frozen_judge():
    for domain, wl in DOMAINS.items():
        bundle = resolve_domain({"workload_id": wl})
        env = bundle.make_env()
        safe = bundle.proposer.propose({"workload_id": wl}, [])
        bad = _violation(domain)

        # The safe tuning candidate is accepted by the domain judge -> gate auto_clears.
        assert not _domain_rejects(bundle, env, safe), f"{domain}: safe candidate unexpectedly rejected"
        assert portable_gate(safe) == "auto_clear", f"{domain}: gate did not clear the safe candidate"

        # The canonical violation is rejected by the domain judge -> gate escalates.
        assert _domain_rejects(bundle, env, bad), f"{domain}: violation not caught by the frozen judge"
        assert portable_gate(bad) == "escalate", f"{domain}: gate did not escalate the violation"
    print("  portable gate matches each domain's frozen judge (safe->clear, violation->escalate): PASS")


if __name__ == "__main__":
    tests = [
        ("postgres membrane abstains cross-domain", test_postgres_membrane_abstains_on_all_foreign_domains),
        ("portable gate matches domain judge", test_portable_gate_matches_each_domains_frozen_judge),
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
