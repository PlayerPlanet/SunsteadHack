#!/usr/bin/env python
"""Deep boundary probe — Haiku optimizes, the frozen pore gates, Sonnet judges.

Generates a labeled governance dataset across multiple drift styles:

    (regime, drift, Haiku proposal)  ->  frozen pore.escalate?  ->  Sonnet approve/reject

and the two boundary readings + the pore-vs-human calibration gap per style.

    export ANTHROPIC_API_KEY=...
    python scripts/run_deep_probe.py                 # real LLM actors
    python scripts/run_deep_probe.py --mock          # deterministic, no API (smoke)
    python scripts/run_deep_probe.py --iterations 24 --styles linear_ramp,burst

No live DB and no DDL on shared Aiven: the latency is modeled (live p99 is proven in
run_phase1_curve.py / run_job_curve.py); this probe proves the governance/boundary
layer at scale with real LLM actors. The frozen pore (cleanroom.pore) is never edited.
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from cleanroom import pore as pore_mod
from cleanroom.benchmark import is_within_noise
from cleanroom.probe import (
    DRIFT_STYLES,
    ProbeRecord,
    baseline_samples,
    calibration_gap,
    drift_schedule,
    longitudinal_curve,
    modeled_samples,
    regime_context,
    spatial_curve,
)
from cleanroom.probe.agents import HAIKU_MODEL, SONNET_MODEL, HaikuOptimizerAgent, SonnetHumanAgent
from cleanroom.types import Candidate

_BASELINE_P99 = 120.0


# --- Deterministic mock actors (for --mock smoke runs and tests) ------------

class MockOptimizer:
    """Drift-driven deterministic proposer: reaches for riskier levers as drift rises."""

    model = "mock-haiku"

    def propose(self, ctx, history):
        d = ctx["drift"]
        if d < 0.30:
            c = Candidate("index", {"table": "cast_info", "columns": ["movie_id"]}, True)
            why = "Calm regime: targeted reversible index on the heavy join key."
        elif d < 0.60:
            c = Candidate("statistics", {"table": "title", "columns": ["production_year", "kind_id"]}, True)
            why = "Shifting regime: extended statistics fix correlated-column estimates."
        elif d < 0.85:
            c = Candidate("guc", {"name": "shared_buffers", "value": "4GB", "blast_radius": "high"}, True)
            why = "Turbulent regime: indexes stopped helping; raise shared_buffers."
        else:
            c = Candidate("migration", {"table": "cast_info", "op": "VACUUM FULL"}, False)
            why = "Regime break: decisive irreversible reclaim to stop the bleeding."
        return c, {"reasoning": why, "tokens": {"input_tokens": 0, "output_tokens": 0}}


class MockHuman:
    """Deterministic human-proxy: conservative under high drift / irreversibility."""

    model = "mock-sonnet"

    def adjudicate(self, candidate, pore_result, ctx):
        risky = (not candidate.reversible) or ctx["drift"] >= 0.80
        if risky:
            return "reject", "Too risky to be wrong about under this uncertainty; defer.", {"tokens": {}}
        return "approve", "Reversible and well-targeted for the regime; acceptable.", {"tokens": {}}


# --- The probe loop for one drift style -------------------------------------

def run_style(style: str, n: int, proposer, human, *, verbose: bool = True) -> list[ProbeRecord]:
    """Run n optimizer steps under `style`'s drift schedule; return labeled records.

    Mirrors the interior loop's decide logic (keep/discard/rollback) on the modeled
    measurement, and adds the human-proxy judgment on every pore escalation. The
    frozen pore is consulted exactly as in production; nothing here can tune it.
    """
    schedule = drift_schedule(style, n)
    records: list[ProbeRecord] = []
    history: list[Candidate] = []
    blocked: list[dict] = []  # previously escalated proposals — to diversify, not forbid
    baseline_p99 = _BASELINE_P99
    base_samp = baseline_samples(baseline_p99)

    for i, drift in enumerate(schedule):
        ctx = regime_context(drift)
        ctx["blocked"] = list(blocked)
        candidate, pmeta = proposer.propose(ctx, history)
        pr = pore_mod.evaluate(candidate)

        rec = ProbeRecord(
            style=style, iteration=i, drift=round(float(drift), 4), regime=ctx["regime"],
            model=getattr(proposer, "model", HAIKU_MODEL), candidate=asdict(candidate),
            proposer_reasoning=pmeta.get("reasoning", ""), pore=pr.pore,
            risk_level=pr.risk_level, escalated=False,
            proposer_tokens=pmeta.get("tokens", {}),
        )

        if pr.requires_human_judgment or pr.decision == "escalate":
            decision, rationale, hmeta = human.adjudicate(candidate, pr, ctx)
            rec.escalated = True
            rec.decision = "escalated"
            rec.human_judge = getattr(human, "model", SONNET_MODEL)
            rec.human_decision = decision
            rec.human_rationale = rationale
            rec.human_tokens = hmeta.get("tokens", {})
            blocked.append(f"{candidate.type} {candidate.params}")
        else:
            cand_samp = modeled_samples(candidate, drift, baseline_p99, i)
            cand_p99 = float(np.percentile(cand_samp, 99))
            within = is_within_noise(base_samp, cand_samp)
            if cand_p99 > baseline_p99:
                decision = "rollback"
            elif within:
                decision = "discard"
            else:
                decision = "keep"
                baseline_p99 = cand_p99
                base_samp = cand_samp
                history.append(candidate)
            rec.baseline_p99 = round(baseline_p99, 3)
            rec.candidate_p99 = round(cand_p99, 3)
            rec.within_noise = within
            rec.decision = decision

        records.append(rec)
        if verbose:
            tag = (f"ESCALATED->{rec.human_decision}" if rec.escalated else rec.decision.upper())
            print(f"  [{style:<12} {i:>2}] drift={drift:.2f} {candidate.type:<10} -> {tag}")
    return records


# --- Reporting --------------------------------------------------------------

def style_readings(style: str, records: list[ProbeRecord]) -> dict:
    return {
        "style": style,
        "n": len(records),
        "escalation_rate": sum(1 for r in records if r.escalated) / len(records),
        "spatial": spatial_curve(records),
        "longitudinal": longitudinal_curve(records),
        "calibration_gap": calibration_gap(records),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deep boundary probe across drift styles.")
    ap.add_argument("--iterations", type=int, default=24, help="Optimizer steps per style.")
    ap.add_argument("--styles", default=",".join(DRIFT_STYLES),
                    help="Comma-separated drift styles (default: all).")
    ap.add_argument("--mock", action="store_true", help="Use deterministic actors (no API).")
    ap.add_argument("--out-dir", default="artifacts/deep_probe")
    ap.add_argument("--workers", type=int, default=6, help="Parallel styles (real-API runs).")
    args = ap.parse_args(argv)

    styles = [s.strip() for s in args.styles.split(",") if s.strip()]
    for s in styles:
        if s not in DRIFT_STYLES:
            print(f"ERROR: unknown style {s!r}; valid: {list(DRIFT_STYLES)}", file=sys.stderr)
            return 2

    if args.mock:
        make_proposer = lambda: MockOptimizer()
        make_human = lambda: MockHuman()
        print("[mock] deterministic actors — no API calls.")
    else:
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("anthropic_api_key")):
            print("ERROR: no ANTHROPIC_API_KEY. Set it or use --mock.", file=sys.stderr)
            return 2
        import anthropic
        client = anthropic.Anthropic()  # shared, thread-safe across requests
        make_proposer = lambda: HaikuOptimizerAgent(client=client)
        make_human = lambda: SonnetHumanAgent(client=client)
        print(f"[live] optimizer={HAIKU_MODEL}  human={SONNET_MODEL}  "
              f"styles={len(styles)} x {args.iterations} steps")

    # Run styles concurrently (each style is an independent sequential loop).
    def _run(style):
        return style, run_style(style, args.iterations, make_proposer(), make_human(),
                                verbose=args.mock)

    results: dict[str, list[ProbeRecord]] = {}
    if args.mock or args.workers <= 1:
        for s in styles:
            results[s] = run_style(s, args.iterations, make_proposer(), make_human(), verbose=True)
    else:
        with ThreadPoolExecutor(max_workers=min(args.workers, len(styles))) as ex:
            for style, recs in ex.map(_run, styles):
                results[style] = recs
                print(f"  done: {style} ({len(recs)} steps, "
                      f"{sum(1 for r in recs if r.escalated)} escalated)")

    all_records = [r for s in styles for r in results[s]]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "dataset.jsonl"
    with dataset_path.open("w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    readings = {
        "config": {"iterations": args.iterations, "styles": styles, "mock": args.mock,
                   "optimizer": "mock-haiku" if args.mock else HAIKU_MODEL,
                   "human": "mock-sonnet" if args.mock else SONNET_MODEL},
        "combined": {
            "n": len(all_records),
            "escalation_rate": sum(1 for r in all_records if r.escalated) / len(all_records),
            "spatial": spatial_curve(all_records),
            "calibration_gap": calibration_gap(all_records),
        },
        "by_style": {s: style_readings(s, results[s]) for s in styles},
    }
    readings_path = out_dir / "readings.json"
    readings_path.write_text(json.dumps(readings, indent=2), encoding="utf-8")

    # Console summary
    print("\n=== COMBINED spatial curve (escalation rate vs drift) ===")
    print("    PROXY / lower bound of the legitimacy boundary — not the true edge")
    for row in readings["combined"]["spatial"]:
        bar = "#" * int(row["escalation_rate"] * 40)
        print(f"  drift={row['drift']:.2f}  {row['escalation_rate']:5.1%}  n={row['n']:>3}  {bar}")
    cg = readings["combined"]["calibration_gap"]
    print(f"\n=== CALIBRATION GAP (the headroom the amortized membrane reclaims) ===")
    print(f"  escalated={cg['n_escalated']}  human_approved={cg['human_approved']}  "
          f"human_rejected={cg['human_rejected']}")
    print(f"  false-stop rate (human approved a stop) = {cg['false_stop_rate']:.1%}")
    print(f"  pore precision  (human confirmed a stop) = {cg['pore_precision']:.1%}")
    print("\n=== Per-style escalation rate & longitudinal shape ===")
    for s in styles:
        sr = readings["by_style"][s]
        spark = "".join("#" if w["ratio"] > 0.5 else ("-" if w["ratio"] > 0 else ".")
                        for w in sr["longitudinal"])
        print(f"  {s:<13} esc={sr['escalation_rate']:5.1%}  longitudinal[{spark}]")

    print(f"\nWrote {len(all_records)} labeled rows -> {dataset_path}")
    print(f"Wrote readings -> {readings_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
