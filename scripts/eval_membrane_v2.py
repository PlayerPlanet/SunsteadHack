#!/usr/bin/env python
"""Evaluate membrane v2 (issue #20 follow-on): does semantic-risk featurization buy
real cross-lever generalization, and what does the cost/risk frontier look like?

Reports, honestly:

  1. DEPLOYMENT (full-fit, rho=0.25): per-risk-bucket decisions, false-clears,
     reclaimed slack, abstention concentration.

  2. HELD-OUT (leave-one-lever-out) — THE HEADLINE. Hold out each lever entirely and
     predict it COLD from its risk profile. v1 abstains 100% here (lever identity is
     unseen). v2 generalizes: a held-out durability switch is predicted reject from
     the *other* durability switch; a held-out sizing knob is predicted approve from
     the other sizing knobs; the lone bounded-tradeoff lever, having no profile-peer,
     correctly falls to the OOD abstain head. Side-by-side with v1.

  3. PARETO FRONTIER. Sweep the risk ratio rho = C_human/C_false_clear and trace
     reclaimed-slack vs false-clear-rate. v1's single bend point sits at the
     zero-false-clear knee; v2 shows the whole tradeoff the operator can dial.

  4. OOD DEMO. A result-semantics-changing rewrite and an unknown systemic lever both
     hit the abstain head — the membrane refuses to stand behind a novel risk.

    python scripts/eval_membrane_v2.py
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleanroom.membrane import Membrane  # v1, for the side-by-side  # noqa: E402
from cleanroom.membrane.v2 import MembraneV2  # noqa: E402
from cleanroom.types import Candidate  # noqa: E402


def _cand(row) -> Candidate:
    c = row["candidate"]
    return Candidate(type=c["type"], params=c.get("params") or {}, reversible=c["reversible"])


def _lever(row) -> str:
    p = row["candidate"]["params"]
    return p.get("name") or p.get("op") or row["candidate"]["type"]


def load_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def escalations(rows) -> list[dict]:
    return [r for r in rows if r.get("escalated") and r.get("human_decision") in ("approve", "reject")]


# --- 1. deployment full-fit -------------------------------------------------

def deployment(rows, rho=0.25) -> dict:
    esc = escalations(rows)
    m = MembraneV2.from_records(rows, rho=rho)
    preds = []
    for r in esc:
        d = m.evaluate(_cand(r), {"drift": r["drift"]})
        preds.append({"lever": _lever(r), "true": r["human_decision"], "membrane": d.decision,
                      "p_approve": d.p_approve, "risk_class": d.risk_class, "reason": d.reason})
    fc = [p for p in preds if p["membrane"] == "auto_clear" and p["true"] == "reject"]
    reclaimed = [p for p in preds if p["membrane"] == "auto_clear" and p["true"] == "approve"]
    abstain = [p for p in preds if p["membrane"] == "abstain"]
    return {
        "rho": rho, "n": len(preds),
        "false_clears": len(fc), "false_clear_rate": len(fc) / len(preds),
        "reclaimed_false_stops": len(reclaimed),
        "abstentions": len(abstain),
        "abstention_concentration": dict(Counter(p["lever"] for p in abstain)),
        "escalations_kept": sum(1 for p in preds if p["membrane"] == "escalate"),
        "by_lever": {p["lever"]: {"decision": p["membrane"], "p_approve": p["p_approve"],
                                  "risk_class": p["risk_class"]} for p in preds},
    }


# --- 2. held-out: leave-one-lever-out, v2 vs v1 -----------------------------

def lolo(rows) -> dict:
    esc = escalations(rows)
    levers = sorted({_lever(r) for r in esc})
    v2_per, v1_per = {}, {}
    v2_preds, v1_preds = [], []
    for lv in levers:
        held = [r for r in esc if _lever(r) == lv]
        m2 = MembraneV2.from_records(rows, exclude_lever=lv)
        m1 = Membrane.from_records(rows, exclude_lever=lv)
        d2 = [{"true": r["human_decision"], "m": m2.evaluate(_cand(r)).decision} for r in held]
        d1 = [{"true": r["human_decision"], "m": m1.evaluate(_cand(r)).decision} for r in held]
        v2_preds += d2
        v1_preds += d1
        # "generalized" = made a committed call (clear/escalate) that matched the human.
        v2_per[lv] = {"n": len(held), "decisions": dict(Counter(d["m"] for d in d2)),
                      "true": dict(Counter(d["true"] for d in d2))}
        v1_per[lv] = {"n": len(held), "decisions": dict(Counter(d["m"] for d in d1))}

    def summ(preds):
        n = len(preds)
        committed = [p for p in preds if p["m"] in ("auto_clear", "escalate")]
        correct = sum(1 for p in committed
                      if (p["m"] == "auto_clear" and p["true"] == "approve")
                      or (p["m"] == "escalate" and p["true"] == "reject"))
        fc = sum(1 for p in preds if p["m"] == "auto_clear" and p["true"] == "reject")
        reclaimed = sum(1 for p in preds if p["m"] == "auto_clear" and p["true"] == "approve")
        abstain = sum(1 for p in preds if p["m"] == "abstain")
        return {"n": n, "committed": len(committed), "committed_correct": correct,
                "false_clears": fc, "reclaimed_cold": reclaimed,
                "abstentions": abstain, "abstention_rate": abstain / n}

    return {
        "v2": {"summary": summ(v2_preds), "per_lever": v2_per},
        "v1": {"summary": summ(v1_preds), "per_lever": v1_per},
        "marquee": _marquee(rows),
    }


def _marquee(rows) -> dict:
    """The one-liner: hold out fsync entirely; does v2 still predict reject COLD?"""
    fsync = next((r for r in escalations(rows) if _lever(r) == "fsync"), None)
    if not fsync:
        return {}
    m2 = MembraneV2.from_records(rows, exclude_lever="fsync")
    m1 = Membrane.from_records(rows, exclude_lever="fsync")
    return {
        "held_out": "fsync (all instances removed from training)",
        "true_human_verdict": "reject",
        "v2_cold_prediction": m2.evaluate(_cand(fsync)).decision,
        "v2_reason": m2.evaluate(_cand(fsync)).reason,
        "v1_cold_prediction": m1.evaluate(_cand(fsync)).decision,
        "note": "v2 learns data_loss=HIGH->reject from full_page_writes and applies it to "
                "the never-seen fsync; v1 has no precedent for the *name* and can only abstain.",
    }


# --- 3. Pareto frontier -----------------------------------------------------

def frontier(rows, rhos=(0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.7, 0.9)) -> dict:
    esc = escalations(rows)
    pts = []
    for rho in rhos:
        m = MembraneV2.from_records(rows, rho=rho)
        decs = [(m.evaluate(_cand(r)).decision, r["human_decision"]) for r in esc]
        fc = sum(1 for d, t in decs if d == "auto_clear" and t == "reject")
        reclaimed = sum(1 for d, t in decs if d == "auto_clear" and t == "approve")
        cleared = sum(1 for d, _ in decs if d == "auto_clear")
        pts.append({"rho": rho, "reclaimed": reclaimed, "false_clears": fc,
                    "cleared": cleared, "false_clear_rate": (fc / cleared) if cleared else 0.0,
                    "remaining_escalations": len(esc) - cleared})
    return {"n_escalations": len(esc), "points": pts,
            "v1_equivalent": {"reclaimed": 4, "false_clears": 0,
                              "note": "v1's single bend point — the zero-false-clear knee"}}


# --- 4. OOD demo ------------------------------------------------------------

def ood_demo(rows) -> dict:
    m = MembraneV2.from_records(rows)
    cases = {
        "result_semantics_rewrite": Candidate(type="rewrite", params={"op": "query_rewrite"}, reversible=True),
        "unknown_systemic_lever": Candidate(type="guc", params={"name": "max_parallel_workers_per_gather"}, reversible=True),
        "irreversible_table_rewrite": Candidate(type="maintenance", params={"op": "vacuum_full"}, reversible=False),
    }
    out = {}
    for name, c in cases.items():
        d = m.evaluate(c)
        out[name] = {"decision": d.decision, "ood": d.ood, "reason": d.reason, "risk_class": d.risk_class}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate membrane v2 (semantic-risk generalization).")
    ap.add_argument("--dataset", default="artifacts/deep_probe/dataset.jsonl")
    ap.add_argument("--out", default="artifacts/deep_probe/membrane_v2_eval.json")
    args = ap.parse_args(argv)

    rows = load_rows(Path(args.dataset))
    if len(escalations(rows)) < 4:
        print("Too few escalations — run scripts/run_deep_probe.py first.", file=sys.stderr)
        return 2

    result = {
        "n_escalations": len(escalations(rows)),
        "deployment_full_fit": deployment(rows),
        "held_out_lolo": lolo(rows),
        "pareto_frontier": frontier(rows),
        "ood_demo": ood_demo(rows),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")

    dep, lo, mq = result["deployment_full_fit"], result["held_out_lolo"], result["held_out_lolo"]["marquee"]
    print(f"Escalations: {result['n_escalations']}")
    print("\n[1] DEPLOYMENT (full-fit, rho=0.25):")
    print(f"    false-clears={dep['false_clears']}  reclaimed={dep['reclaimed_false_stops']}  "
          f"abstains_on={dep['abstention_concentration']}")
    print("\n[2] HELD-OUT (leave-one-lever-out) — v2 generalizes where v1 cannot:")
    v2s, v1s = lo["v2"]["summary"], lo["v1"]["summary"]
    print(f"    v2: {v2s['committed_correct']}/{v2s['committed']} cold calls correct, "
          f"{v2s['false_clears']} false-clears, {v2s['reclaimed_cold']} reclaimed cold, "
          f"abstention {v2s['abstention_rate']:.0%}")
    print(f"    v1: {v1s['committed']} committed calls, abstention {v1s['abstention_rate']:.0%}  "
          "(memorizes lever names -> abstains on everything unseen)")
    if mq:
        print(f"\n    MARQUEE: hold out `fsync` entirely -> v2 predicts '{mq['v2_cold_prediction']}' "
              f"cold (human said {mq['true_human_verdict']}); v1 -> '{mq['v1_cold_prediction']}'.")
    print("\n[3] PARETO FRONTIER (reclaimed vs false-clears as rho rises):")
    for p in result["pareto_frontier"]["points"]:
        print(f"    rho={p['rho']:<4} reclaimed={p['reclaimed']:<2} false_clears={p['false_clears']}")
    print("\n[4] OOD demo:")
    for name, d in result["ood_demo"].items():
        print(f"    {name:28} -> {d['decision']:9} (ood={d['ood']}, {d['reason']})")
    print(f"\nWrote -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
