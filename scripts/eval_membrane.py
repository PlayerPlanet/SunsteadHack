#!/usr/bin/env python
"""Evaluate the shadow membrane and draw the bend graph (issue #20, Phase 2).

Reads the probe's labelled escalations and reports, honestly:

  1. HELD-OUT (leave-one-lever-out): hold out an entire lever family, predict it
     cold. The membrane has no precedent -> it ABSTAINS on every held-out lever.
     => false-clear rate on held-out = 0 (it never auto-clears something unseen).
     This is the abstain head working: confronted with a novel lever it asks a
     human rather than guessing. (It is also why the held-out split is
     leave-one-lever-out, NOT held-out-regime: the frozen pore concentrates 100%
     of escalations in the `regime_break` tier — the only tier whose option menu
     offers systemic levers — so a held-out-regime split has zero training labels.)

  2. IN-PRECEDENT (leave-one-out within seen levers): the deployment-realistic
     case — the membrane has seen these levers before in the governance log.
     Reports reclaimed false-stops, abstention concentration, and calibration
     (reliability + ECE).

  3. THE BEND GRAPH: cumulative escalations vs work, frozen pore vs membrane-shadow.
     The membrane curve bends below the frozen line by exactly the clean-precedent
     slack it reclaims (auto_clears); abstentions and escalates still count as
     escalations. The membrane never acted — the bend is measured against the
     frozen ruler, not produced by moving it.

    python scripts/eval_membrane.py
    python scripts/eval_membrane.py --dataset artifacts/deep_probe/dataset.jsonl
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleanroom.membrane import Membrane  # noqa: E402
from cleanroom.types import Candidate  # noqa: E402


def _candidate(row) -> Candidate:
    c = row["candidate"]
    return Candidate(type=c["type"], params=c.get("params") or {}, reversible=c["reversible"])


def load_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def escalations(rows) -> list[dict]:
    return [r for r in rows if r.get("escalated") and r.get("human_decision") in ("approve", "reject")]


# --- 1. held-out: leave-one-lever-out ---------------------------------------

def leave_one_lever_out(rows) -> dict:
    """Hold out each lever family entirely; predict it with a membrane that never
    saw it. Records the membrane's shadow decision vs the human's true verdict."""
    esc = escalations(rows)
    levers = sorted({_lever(r) for r in esc})  # every lever that ever escalated
    per_lever, all_preds = {}, []
    for lv in levers:
        held = [r for r in esc if _lever(r) == lv]
        m = Membrane.from_records(rows, exclude_lever=lv)  # fit WITHOUT this lever
        decs = []
        for r in held:
            d = m.evaluate(_candidate(r), {"drift": r["drift"]})
            decs.append({"true": r["human_decision"], "membrane": d.decision,
                         "p_approve": d.p_approve, "reason": d.reason})
            all_preds.append((r["human_decision"], d.decision))
        per_lever[lv] = {
            "n": len(held),
            "true": dict(Counter(d["true"] for d in decs)),
            "membrane": dict(Counter(d["membrane"] for d in decs)),
        }
    n = len(all_preds)
    false_clears = sum(1 for true, dec in all_preds if dec == "auto_clear" and true == "reject")
    auto_clears = sum(1 for _, dec in all_preds if dec == "auto_clear")
    abstains = sum(1 for _, dec in all_preds if dec == "abstain")
    return {
        "protocol": "leave-one-lever-out (each lever predicted by a membrane that never saw it)",
        "n": n,
        "false_clears": false_clears,
        "false_clear_rate": false_clears / n if n else 0.0,
        "auto_clears": auto_clears,
        "abstentions": abstains,
        "abstention_rate": abstains / n if n else 0.0,
        "per_lever": per_lever,
    }


def _lever(row) -> str:
    p = row["candidate"]["params"]
    return p.get("name") or p.get("op") or row["candidate"]["type"]


# --- 1b. deployment: the full-fit gate (what the bend graph rides on) -------

def deployment_full_fit(rows) -> dict:
    """The realistic shadow deployment: the membrane has the whole governance log as
    precedent. Reports the gate's actual decision on every escalation — this is the
    behaviour the bend graph and the DoD ride on (0 false-clears by construction:
    a lever with any reject in its record is never auto-cleared)."""
    esc = escalations(rows)
    m = Membrane.from_records(rows)
    preds = []
    for r in esc:
        d = m.evaluate(_candidate(r), {"drift": r["drift"]})
        preds.append({"lever": _lever(r), "true": r["human_decision"],
                      "membrane": d.decision, "p_approve": round(d.p_approve, 3),
                      "reason": d.reason})
    n = len(preds)
    false_clears = [p for p in preds if p["membrane"] == "auto_clear" and p["true"] == "reject"]
    reclaimed = [p for p in preds if p["membrane"] == "auto_clear" and p["true"] == "approve"]
    abstain = [p for p in preds if p["membrane"] == "abstain"]
    escalate = [p for p in preds if p["membrane"] == "escalate"]
    by_lever = {}
    for p in preds:
        slot = by_lever.setdefault(p["lever"], {"decision": p["membrane"], "p_approve": p["p_approve"],
                                                "true": Counter()})
        slot["true"][p["true"]] += 1
    for slot in by_lever.values():
        slot["true"] = dict(slot["true"])
    return {
        "protocol": "full-fit on all labels (deployment-realistic shadow precedent)",
        "n": n,
        "false_clears": len(false_clears),
        "false_clear_rate": len(false_clears) / n if n else 0.0,
        "reclaimed_false_stops": len(reclaimed),
        "abstentions": len(abstain),
        "abstention_concentration": dict(Counter(p["lever"] for p in abstain)),
        "escalations_kept": len(escalate),
        "by_lever": by_lever,
    }


# --- 2. in-precedent: leave-one-out within seen levers ----------------------

def in_precedent_loo(rows) -> dict:
    """Standard LOO: predict each escalation with a membrane fit on the other 14.
    The realistic deployment case (the lever has precedent in the log)."""
    esc = escalations(rows)
    preds = []
    for i, r in enumerate(esc):
        others = [o for j, o in enumerate(esc) if j != i]
        m = Membrane.from_records(others)
        d = m.evaluate(_candidate(r), {"drift": r["drift"]})
        preds.append({"lever": _lever(r), "true": r["human_decision"],
                      "membrane": d.decision, "p_approve": d.p_approve, "reason": d.reason})

    n = len(preds)
    false_clears = [p for p in preds if p["membrane"] == "auto_clear" and p["true"] == "reject"]
    reclaimed = [p for p in preds if p["membrane"] == "auto_clear" and p["true"] == "approve"]
    abstain = [p for p in preds if p["membrane"] == "abstain"]
    escalate = [p for p in preds if p["membrane"] == "escalate"]
    abstain_levers = dict(Counter(p["lever"] for p in abstain))

    return {
        "protocol": "leave-one-out within seen levers (deployment-realistic)",
        "n": n,
        "false_clears": len(false_clears),
        "false_clear_rate": len(false_clears) / n if n else 0.0,
        "reclaimed_false_stops": len(reclaimed),
        "abstentions": len(abstain),
        "abstention_concentration": abstain_levers,
        "escalations_kept": len(escalate),
        "calibration": _calibration(preds),
        "predictions": preds,
    }


def _calibration(preds, bins=5) -> dict:
    """Reliability table + expected calibration error over the LOO approve-probs.
    Crude on n~=15 — reported with that caveat — but it is the right shape."""
    buckets = defaultdict(lambda: {"n": 0, "approve": 0, "p_sum": 0.0})
    for p in preds:
        if p["p_approve"] is None:
            continue
        b = min(bins - 1, int(p["p_approve"] * bins))
        buckets[b]["n"] += 1
        buckets[b]["approve"] += 1 if p["true"] == "approve" else 0
        buckets[b]["p_sum"] += p["p_approve"]
    total = sum(b["n"] for b in buckets.values())
    table, ece = [], 0.0
    for b in sorted(buckets):
        d = buckets[b]
        conf = d["p_sum"] / d["n"]
        acc = d["approve"] / d["n"]  # observed approve frequency in this bin
        ece += (d["n"] / total) * abs(conf - acc)
        table.append({"bin": f"{b / bins:.1f}-{(b + 1) / bins:.1f}", "n": d["n"],
                      "mean_p_approve": round(conf, 3), "observed_approve_rate": round(acc, 3)})
    return {"ece": round(ece, 4), "reliability": table, "note": f"n={total} — crude but honest"}


# --- 3. the bend graph ------------------------------------------------------

def bend_curve(rows) -> dict:
    """Cumulative escalations vs cumulative work: frozen pore vs membrane-shadow.

    Frozen line uses the dataset's `escalated` flag as-is. Membrane line removes the
    membrane's auto_clears from the escalation stream (abstentions + escalates still
    count). Uses the FULL-fit membrane (deployment-realistic precedent). The strict
    held-out (leave-one-lever-out) membrane abstains on everything -> its curve is
    identical to frozen (no bend) -> reported as the honesty guardrail."""
    ordered = list(rows)  # file order = per-style, iteration order within style
    full = Membrane.from_records(rows)

    frozen_cum, membrane_cum, work = [], [], []
    f = mloss = 0
    auto_cleared = []
    for k, r in enumerate(ordered, start=1):
        esc = bool(r.get("escalated") and r.get("human_decision") in ("approve", "reject"))
        f += 1 if esc else 0
        m_esc = esc
        if esc:
            d = full.evaluate(_candidate(r), {"drift": r["drift"]})
            if d.decision == "auto_clear":
                m_esc = False  # membrane would have waved this through (shadow)
                auto_cleared.append({"lever": _lever(r), "true": r["human_decision"],
                                     "p_approve": d.p_approve})
        mloss += 1 if m_esc else 0
        work.append(k)
        frozen_cum.append(f)
        membrane_cum.append(mloss)

    return {
        "work": work,
        "frozen_cumulative_escalations": frozen_cum,
        "membrane_cumulative_escalations": membrane_cum,
        "frozen_total": frozen_cum[-1] if frozen_cum else 0,
        "membrane_total": membrane_cum[-1] if membrane_cum else 0,
        "reclaimed": auto_cleared,
        "reduction_pct": round(100 * (1 - membrane_cum[-1] / frozen_cum[-1]), 1) if frozen_cum and frozen_cum[-1] else 0.0,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate the shadow membrane and draw the bend graph.")
    ap.add_argument("--dataset", default="artifacts/deep_probe/dataset.jsonl")
    ap.add_argument("--out", default="artifacts/deep_probe/membrane_eval.json")
    args = ap.parse_args(argv)

    rows = load_rows(Path(args.dataset))
    esc = escalations(rows)
    if len(esc) < 4:
        print(f"Only {len(esc)} escalations — run scripts/run_deep_probe.py first.", file=sys.stderr)
        return 2

    result = {
        "n_rows": len(rows),
        "n_escalations": len(esc),
        "deployment_full_fit": deployment_full_fit(rows),
        "held_out_leave_one_lever_out": leave_one_lever_out(rows),
        "in_precedent_loo": in_precedent_loo(rows),
        "bend": bend_curve(rows),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")

    dep = result["deployment_full_fit"]
    ho = result["held_out_leave_one_lever_out"]
    ip = result["in_precedent_loo"]
    bd = result["bend"]
    print(f"Escalations: {len(esc)}")
    print("\n[1] DEPLOYMENT (full-fit shadow gate — what the bend rides on):")
    print(f"    false-clear rate      = {dep['false_clear_rate']:.1%}  ({dep['false_clears']}/{dep['n']})")
    print(f"    reclaimed false-stops = {dep['reclaimed_false_stops']}")
    print(f"    escalations kept      = {dep['escalations_kept']}")
    print(f"    abstains on           = {dep['abstention_concentration']}")
    print("\n[2] HELD-OUT (leave-one-lever-out — the honesty guardrail):")
    print(f"    false-clear rate = {ho['false_clear_rate']:.1%}  ({ho['false_clears']}/{ho['n']})  "
          f"abstention = {ho['abstention_rate']:.1%}")
    print("    -> on a never-seen lever the membrane abstains; it never auto-clears blind.")
    print("\n[3] IN-PRECEDENT LOO (calibration / robustness stress on n=15):")
    print(f"    false-clear rate    = {ip['false_clear_rate']:.1%}  ({ip['false_clears']}/{ip['n']})"
          "  <- the lone synchronous_commit reject, the published 93.3% residual")
    print(f"    calibration ECE     = {ip['calibration']['ece']}")
    print("\n[4] BEND: frozen escalations {} -> membrane-shadow {}  ({}% reclaimed, {} false-clears)".format(
        bd["frozen_total"], bd["membrane_total"], bd["reduction_pct"], dep["false_clears"]))
    print(f"\nWrote -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
