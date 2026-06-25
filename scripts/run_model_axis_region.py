#!/usr/bin/env python
"""Model-axis experiment: how does the PROPOSER LLM move the escalation region?

Holds everything frozen except the proposer:
  * frozen pore (cleanroom.pore)            — the gate, unchanged
  * human-proxy judge (claude-sonnet-4-6)   — same accountable adjudicator for all
  * modeled benchmark + drift schedules     — identical worlds

and swaps ONLY the optimizer LLM. The "region" is the spatial boundary curve —
escalation rate vs world-drift. Overlaying it per proposer shows how the choice of
backend model moves where the agent leaves the region it can act in unsupervised.

Every model is driven through the SAME Anthropic-SDK tool-use path (so the comparison
is not confounded by different output parsing). MiniMax speaks the Anthropic API, so it
plugs in via base_url/api_key — no separate client. Credentials are read from the
environment at runtime; this script never prints them.

    export ANTHROPIC_API_KEY=...
    # optional cross-vendor: export MINIMAX_API_KEY=...  MINIMAX_BASE_URL=...
    python scripts/run_model_axis_region.py --models haiku-4.5,sonnet-4.6,opus-4.5
    python scripts/run_model_axis_region.py --models all --styles linear_ramp,accel_creep --iterations 24
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleanroom.probe import DRIFT_STYLES, calibration_gap, spatial_curve
from cleanroom.probe.agents import HaikuOptimizerAgent, SonnetHumanAgent
from run_deep_probe import run_style  # reuse the exact frozen-pore probe loop

# The proposer ladder. backend selects the client; model is the API model id.
# label is what appears in the overlay. Anthropic + MiniMax both go through the SDK.
MODEL_LADDER = [
    {"label": "haiku-4.5", "backend": "anthropic", "model": "claude-haiku-4-5"},
    {"label": "sonnet-4.6", "backend": "anthropic", "model": "claude-sonnet-4-6"},
    {"label": "opus-4.5", "backend": "anthropic", "model": "claude-opus-4-5"},
    {"label": "minimax-m2.5", "backend": "minimax", "model": "MiniMax-M2.5"},
    {"label": "minimax-m3", "backend": "minimax", "model": "MiniMax-M3"},
]
HUMAN_MODEL = "claude-sonnet-4-6"  # the fixed accountable judge for every run


def _client(backend: str):
    import anthropic

    if backend == "anthropic":
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("anthropic_api_key")):
            raise RuntimeError("no ANTHROPIC_API_KEY in environment")
        return anthropic.Anthropic()
    if backend == "minimax":
        key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("minimax_api_key")
        base = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/anthropic")
        if not key:
            raise RuntimeError("no MINIMAX_API_KEY in environment (set it + MINIMAX_BASE_URL)")
        return anthropic.Anthropic(api_key=key, base_url=base)
    raise ValueError(f"unknown backend {backend!r}")


def run_one_model(spec: dict, styles: list[str], iterations: int, human_client) -> dict | None:
    """Run the full probe for one proposer model; return its region reading or None."""
    try:
        prop_client = _client(spec["backend"])
        proposer = HaikuOptimizerAgent(model=spec["model"], client=prop_client)
        # Smoke one call so a missing key / unsupported tool-use fails fast & clearly.
        human = SonnetHumanAgent(model=HUMAN_MODEL, client=human_client)
    except Exception as e:  # noqa: BLE001
        print(f"[skip] {spec['label']}: {e}", file=sys.stderr)
        return None

    # The proposer carries its label as `.model` so records are tagged per model.
    proposer.model = spec["model"]
    all_records = []
    try:
        for style in styles:
            recs = run_style(style, iterations, proposer, human, verbose=False)
            all_records.extend(recs)
            esc = sum(1 for r in recs if r.escalated)
            print(f"  [{spec['label']}] {style:<12} {len(recs)} steps, {esc} escalated")
    except Exception as e:  # noqa: BLE001
        print(f"[fail] {spec['label']} during run: {e}", file=sys.stderr)
        if not all_records:
            return None

    cg = calibration_gap(all_records)
    return {
        "label": spec["label"], "model": spec["model"], "backend": spec["backend"],
        "n": len(all_records),
        "escalation_rate": sum(1 for r in all_records if r.escalated) / len(all_records),
        "spatial": spatial_curve(all_records),
        "calibration_gap": cg,
        "records": [asdict(r) for r in all_records],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sweep the proposer LLM; measure the escalation region.")
    ap.add_argument("--models", default="haiku-4.5,sonnet-4.6,opus-4.5",
                    help="comma-separated labels from the ladder, or 'all'.")
    ap.add_argument("--styles", default="linear_ramp,accel_creep,oscillating",
                    help="drift styles spanning 0->1 (for clean region coverage).")
    ap.add_argument("--iterations", type=int, default=20, help="optimizer steps per style.")
    ap.add_argument("--out-dir", default="artifacts/model_axis")
    ap.add_argument("--workers", type=int, default=3, help="models run concurrently.")
    args = ap.parse_args(argv)

    labels = [m["label"] for m in MODEL_LADDER] if args.models == "all" else \
        [s.strip() for s in args.models.split(",") if s.strip()]
    specs = [m for m in MODEL_LADDER if m["label"] in labels]
    if not specs:
        print(f"no known models in {labels}; ladder={[m['label'] for m in MODEL_LADDER]}", file=sys.stderr)
        return 2
    styles = [s.strip() for s in args.styles.split(",") if s.strip()]
    for s in styles:
        if s not in DRIFT_STYLES:
            print(f"unknown style {s!r}; valid {list(DRIFT_STYLES)}", file=sys.stderr)
            return 2

    import anthropic
    human_client = anthropic.Anthropic()  # fixed judge, shared & thread-safe

    print(f"[model-axis] proposers={[s['label'] for s in specs]}  human={HUMAN_MODEL}  "
          f"styles={styles} x {args.iterations}  (frozen pore + judge + benchmark)")

    results = []
    if args.workers <= 1:
        for spec in specs:
            r = run_one_model(spec, styles, args.iterations, human_client)
            if r:
                results.append(r)
    else:
        with ThreadPoolExecutor(max_workers=min(args.workers, len(specs))) as ex:
            for r in ex.map(lambda sp: run_one_model(sp, styles, args.iterations, human_client), specs):
                if r:
                    results.append(r)

    if not results:
        print("no model produced results (check credentials).", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        (out_dir / f"dataset_{r['label']}.jsonl").write_text(
            "\n".join(json.dumps(rec, ensure_ascii=False) for rec in r["records"]), encoding="utf-8")
    summary = {
        "config": {"human": HUMAN_MODEL, "styles": styles, "iterations": args.iterations},
        "models": [{k: r[k] for k in ("label", "model", "backend", "n", "escalation_rate",
                                      "spatial", "calibration_gap")} for r in results],
    }
    (out_dir / "regions.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Console overlay of the region (escalation rate vs drift) per proposer.
    print("\n=== THE REGION: escalation rate vs drift, per proposer ===")
    drifts = sorted({row["drift"] for r in results for row in r["spatial"]})
    head = "drift " + "".join(f"{r['label']:>14}" for r in results)
    print(head)
    for d in drifts:
        cells = []
        for r in results:
            hit = next((row for row in r["spatial"] if row["drift"] == d), None)
            cells.append(f"{hit['escalation_rate']:>13.0%}" if hit else f"{'·':>13}")
        print(f"{d:>4.2f} " + " ".join(cells))
    print("\n=== overall escalation rate & false-stop rate (human approved a stop) ===")
    for r in results:
        cg = r["calibration_gap"]
        print(f"  {r['label']:<14} esc={r['escalation_rate']:5.1%}  "
              f"escalations={cg['n_escalated']:>3}  false-stop={cg['false_stop_rate']:5.1%}")
    print(f"\nWrote per-model datasets + regions.json -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
