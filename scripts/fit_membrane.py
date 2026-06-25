#!/usr/bin/env python
"""Capstone: is the calibration gap actually *learnable* from the probe dataset?

The deep probe leaves a labeled set of escalations: (proposal features) -> the
human's approve/reject verdict. The manifesto's bet is that an amortized membrane
could learn to predict that verdict and auto-clear the false stops. Here we test
the bet directly — and honestly, given only ~15 escalations:

  * leave-one-out (LOO), so every reported number is out-of-sample on n=15;
  * a TRANSPARENT per-lever majority baseline (no ML magic), and
  * a generically-featurized logistic regression (one-hot lever + reversible +
    drift — the answer is NOT baked into the features).

The point is not a production model on 15 rows; it is to show the slack is almost
entirely separable, and that the residual error lands exactly on the genuinely
ambiguous lever (synchronous_commit) — i.e. on the irreducible judgment the frozen
proxy can never hold and a human/the membrane must.

    python scripts/fit_membrane.py
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np


def _lever(row) -> str:
    p = row["candidate"]["params"]
    return p.get("name") or p.get("op") or row["candidate"]["type"]


def load_escalations(dataset_path: Path) -> list[dict]:
    rows = [json.loads(l) for l in dataset_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if r.get("escalated") and r.get("human_decision") in ("approve", "reject")]


def featurize(esc: list[dict]):
    """Generic features: one-hot lever + reversible + drift. y=1 approve, 0 reject."""
    levers = sorted({_lever(r) for r in esc})
    idx = {lv: i for i, lv in enumerate(levers)}
    X, y = [], []
    for r in esc:
        row = [0.0] * len(levers)
        row[idx[_lever(r)]] = 1.0
        row += [1.0 if r["candidate"]["reversible"] else 0.0, float(r["drift"])]
        X.append(row)
        y.append(1 if r["human_decision"] == "approve" else 0)
    return np.array(X), np.array(y), levers


def loo_majority(esc: list[dict]) -> dict:
    """Leave-one-out per-lever majority vote — the transparent baseline."""
    correct, errors = 0, []
    for i, r in enumerate(esc):
        lv = _lever(r)
        votes = Counter(o["human_decision"] for j, o in enumerate(esc) if j != i and _lever(o) == lv)
        pred = votes.most_common(1)[0][0] if votes else "reject"  # unseen lever -> conservative
        if pred == r["human_decision"]:
            correct += 1
        else:
            errors.append({"lever": lv, "true": r["human_decision"], "pred": pred, "drift": r["drift"]})
    return {"accuracy": correct / len(esc), "correct": correct, "n": len(esc), "errors": errors}


def loo_logistic(X, y, esc) -> dict:
    from sklearn.linear_model import LogisticRegression
    correct, errors = 0, []
    for i in range(len(y)):
        mask = np.arange(len(y)) != i
        if len(set(y[mask].tolist())) < 2:  # degenerate fold (one class) — skip honestly
            pred = int(round(float(y[mask].mean())))
        else:
            clf = LogisticRegression(C=0.5, max_iter=1000)
            clf.fit(X[mask], y[mask])
            pred = int(clf.predict(X[i:i + 1])[0])
        true = int(y[i])
        if pred == true:
            correct += 1
        else:
            errors.append({"lever": _lever(esc[i]), "true": "approve" if true else "reject",
                           "pred": "approve" if pred else "reject", "drift": esc[i]["drift"]})
    return {"accuracy": correct / len(y), "correct": correct, "n": len(y), "errors": errors}


def lever_separability(esc: list[dict]) -> dict:
    """Per-lever approve/reject counts — shows what the verdict is separable on."""
    by = defaultdict(lambda: {"approve": 0, "reject": 0})
    for r in esc:
        by[_lever(r)][r["human_decision"]] += 1
    return {lv: dict(c) for lv, c in sorted(by.items())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fit a tiny membrane on the probe's escalation labels.")
    ap.add_argument("--dataset", default="artifacts/deep_probe/dataset.jsonl")
    ap.add_argument("--out", default="artifacts/deep_probe/membrane_fit.json")
    args = ap.parse_args(argv)

    esc = load_escalations(Path(args.dataset))
    if len(esc) < 4:
        print(f"Only {len(esc)} escalations — too few to fit. Run the probe first.", file=sys.stderr)
        return 2

    base = loo_majority(esc)
    sep = lever_separability(esc)
    X, y, levers = featurize(esc)
    logit = loo_logistic(X, y, esc)

    n_approve = sum(1 for r in esc if r["human_decision"] == "approve")
    majority_class = max(n_approve, len(esc) - n_approve) / len(esc)

    result = {
        "n_escalated": len(esc), "n_approve": n_approve, "n_reject": len(esc) - n_approve,
        "majority_class_baseline": majority_class,
        "loo_per_lever_majority": base, "loo_logistic": logit,
        "lever_separability": sep, "features": levers + ["reversible", "drift"],
    }
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Escalations: {len(esc)}  (approve={n_approve}, reject={len(esc) - n_approve})")
    print(f"Majority-class floor:          {majority_class:5.1%}")
    print(f"LOO per-lever majority:        {base['accuracy']:5.1%}  ({base['correct']}/{base['n']})")
    print(f"LOO logistic (one-hot+rev+drift): {logit['accuracy']:5.1%}  ({logit['correct']}/{logit['n']})")
    print("\nVerdict is separable on the proposed lever:")
    for lv, c in sep.items():
        print(f"  {lv:<20} approve={c['approve']}  reject={c['reject']}")
    print("\nResidual LOO errors (where judgment is irreducible):")
    for e in (base["errors"] or [{"lever": "(none)", "true": "-", "pred": "-", "drift": 0}]):
        print(f"  {e['lever']:<20} true={e['true']:<8} pred={e['pred']:<8} drift={e['drift']}")
    print(f"\nWrote -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
