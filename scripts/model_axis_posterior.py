#!/usr/bin/env python
"""Bayesian posterior over the proposer models' escalation behaviour (model-axis).

The point-estimate region curves are noisy (modest n, real-LLM sampling). This turns
each model's escalation rate into a POSTERIOR with a credible interval, so we can say
honestly whether the separation between proposers is real given the data — instead of
over-reading single percentages.

Model: each optimizer step is a Bernoulli escalation. With a Jeffreys prior
Beta(0.5, 0.5), the posterior over a model's escalation probability p is
Beta(0.5 + escalations, 0.5 + non_escalations). Same for the false-stop probability
(among escalations, the fraction the human approved) and the high-drift escalation
rate (drift >= 0.8 — where the boundary actually lives).

Reports per metric:
  * posterior mean + 95% credible interval,
  * P(model has the HIGHEST rate) — joint Monte-Carlo over all models,
  * pairwise P(rate_i > rate_j).

    python scripts/model_axis_posterior.py
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import beta as beta_dist

ALPHA0 = BETA0 = 0.5  # Jeffreys prior
DRAWS = 200_000
HIGH_DRIFT = 0.8


def _load_models(in_dir: Path) -> list[dict]:
    reg = json.loads((in_dir / "regions.json").read_text(encoding="utf-8"))
    out = []
    for m in reg["models"]:
        ds = in_dir / f"dataset_{m['label']}.jsonl"
        recs = [json.loads(l) for l in ds.read_text(encoding="utf-8").splitlines() if l.strip()]
        esc = [r for r in recs if r.get("escalated")]
        esc_labeled = [r for r in esc if r.get("human_decision") in ("approve", "reject")]
        hi = [r for r in recs if r.get("drift", 0) >= HIGH_DRIFT]
        out.append({
            "label": m["label"], "backend": m.get("backend", "?"),
            "n": len(recs), "esc": len(esc),
            "fs_n": len(esc_labeled),
            "fs_k": sum(1 for r in esc_labeled if r["human_decision"] == "approve"),
            "hi_n": len(hi), "hi_k": sum(1 for r in hi if r.get("escalated")),
        })
    return out


def _posterior(models, k_key, n_key, rng) -> dict:
    """Beta posterior per model for a binomial rate; CrI + ranking + dominance."""
    labels = [m["label"] for m in models]
    a = np.array([ALPHA0 + m[k_key] for m in models], dtype=float)
    b = np.array([BETA0 + (m[n_key] - m[k_key]) for m in models], dtype=float)
    # exact credible intervals + means
    table = []
    for i, m in enumerate(models):
        mean = a[i] / (a[i] + b[i])
        lo, hi = beta_dist.ppf([0.025, 0.975], a[i], b[i])
        table.append({"label": m["label"], "backend": m["backend"],
                      "k": int(m[k_key]), "n": int(m[n_key]),
                      "mean": round(float(mean), 4),
                      "ci95": [round(float(lo), 4), round(float(hi), 4)]})
    # joint Monte-Carlo for ranking + pairwise dominance
    draws = np.stack([rng.beta(a[i], b[i], DRAWS) for i in range(len(models))], axis=1)  # (DRAWS, M)
    argmax = draws.argmax(axis=1)
    p_highest = {labels[i]: round(float((argmax == i).mean()), 4) for i in range(len(models))}
    dominance = {}
    for i in range(len(models)):
        for j in range(len(models)):
            if i != j:
                dominance[f"{labels[i]}>{labels[j]}"] = round(float((draws[:, i] > draws[:, j]).mean()), 4)
    return {"table": table, "p_highest": p_highest, "dominance": dominance}


def _forest_svg(table, title, w=720, h=None):
    rows = table
    h = h or (70 + 34 * len(rows))
    pad_l, pad_r, pad_t, pad_b = 130, 30, 40, 36
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
    xmax = min(1.0, max(0.05, max(r["ci95"][1] for r in rows) * 1.1))

    def x(v):
        return pad_l + (v / xmax) * pw
    grid = []
    ticks = [t for t in (0, 0.25, 0.5, 0.75, 1.0) if t <= xmax + 1e-9]
    for t in ticks:
        grid.append(f'<line x1="{x(t):.1f}" y1="{pad_t}" x2="{x(t):.1f}" y2="{pad_t + ph}" class="grid"/>'
                    f'<text x="{x(t):.1f}" y="{pad_t + ph + 18}" class="xtick" text-anchor="middle">{int(t*100)}%</text>')
    body = []
    for i, r in enumerate(rows):
        cy = pad_t + 18 + i * 34
        lo, hi = r["ci95"]
        body.append(
            f'<text x="{pad_l - 10}" y="{cy + 4:.1f}" class="rowlab" text-anchor="end">{r["label"]}</text>'
            f'<line x1="{x(lo):.1f}" y1="{cy:.1f}" x2="{x(hi):.1f}" y2="{cy:.1f}" class="whisk"/>'
            f'<line x1="{x(lo):.1f}" y1="{cy-5:.1f}" x2="{x(lo):.1f}" y2="{cy+5:.1f}" class="cap"/>'
            f'<line x1="{x(hi):.1f}" y1="{cy-5:.1f}" x2="{x(hi):.1f}" y2="{cy+5:.1f}" class="cap"/>'
            f'<circle cx="{x(r["mean"]):.1f}" cy="{cy:.1f}" r="4.5" class="dot"/>'
            f'<text x="{x(hi):.1f}" y="{cy - 8:.1f}" class="val">{r["mean"]*100:.0f}% '
            f'[{lo*100:.0f}–{hi*100:.0f}]</text>')
    return f'''<svg viewBox="0 0 {w} {h}" role="img" aria-label="{title}">
  <text x="{pad_l}" y="20" class="title">{title}</text>
  {''.join(grid)}{''.join(body)}
</svg>'''


def build_html(res) -> str:
    def section(key, title, axis):
        p = res[key]
        dom = p["dominance"]
        # a compact dominance highlight: the most-confident ordering
        return (f'<h2>{title}</h2><div class="fig">{_forest_svg(p["table"], axis)}</div>'
                f'<p class="muted">P(highest): ' +
                ", ".join(f"<b>{k}</b> {v:.0%}" for k, v in sorted(p["p_highest"].items(), key=lambda kv: -kv[1])) +
                "</p>")
    return f'''<title>Model axis — posterior over the escalation region</title>
<style>
  :root {{ --ground:#14171c; --panel:#1b1f27; --ink:#e9ebef; --muted:#8b94a3; --faint:#5b6573;
    --hair:#2a3039; --ember:#e8732c; --serif:Georgia,serif;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; --mono:ui-monospace,Consolas,monospace; }}
  *{{box-sizing:border-box}} body{{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);line-height:1.6}}
  .wrap{{max-width:900px;margin:0 auto;padding:clamp(28px,5vw,64px) clamp(20px,4vw,44px)}}
  .eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--ember);margin:0 0 20px}}
  h1{{font-family:var(--serif);font-weight:400;font-size:clamp(26px,5vw,42px);line-height:1.12;margin:0 0 16px}}
  h1 em{{font-style:italic;color:var(--ember)}} h2{{font-family:var(--serif);font-weight:400;font-size:22px;margin:40px 0 8px}}
  .lede{{font-size:17px;color:var(--muted);max-width:64ch}}
  .fig{{background:var(--panel);border:1px solid var(--hair);border-radius:12px;padding:14px;margin:14px 0;overflow-x:auto}}
  svg{{width:100%;height:auto;min-width:520px}} .muted{{color:var(--muted);font-size:14px}}
  .title{{fill:var(--ink);font:600 14px var(--sans)}} .grid{{stroke:var(--hair)}} .xtick{{fill:var(--muted);font:11px var(--mono)}}
  .rowlab{{fill:var(--ink);font:13px var(--mono)}} .whisk{{stroke:var(--ember);stroke-width:2.5}} .cap{{stroke:var(--ember);stroke-width:2}}
  .dot{{fill:#fff;stroke:var(--ember);stroke-width:2}} .val{{fill:var(--muted);font:11px var(--mono)}}
  .caveat{{background:#212732;border-left:3px solid var(--ember);border-radius:0 8px 8px 0;padding:14px 18px;color:var(--muted);font-size:14px;margin:28px 0}}
  p{{max-width:68ch}}
</style>
<div class="wrap">
  <p class="eyebrow">Boundary Instrument · model axis · posterior</p>
  <h1>How sure are we the proposers <em>actually differ</em>?</h1>
  <p class="lede">Point estimates are noisy at this n. Each model's escalation behaviour is shown
  as a Beta-Binomial posterior (Jeffreys prior) — mean and 95% credible interval. Overlapping
  intervals mean the apparent difference may be sampling noise; separated ones mean it is real.</p>
  {section("escalation", "Escalation rate (all drift) — posterior mean & 95% CrI", "escalation probability")}
  {section("high_drift", "High-drift escalation rate (drift ≥ 0.8) — where the boundary lives", "escalation probability")}
  {section("false_stop", "False-stop rate (human approved the stop) — reclaimable slack", "false-stop probability")}
  <div class="caveat">Jeffreys prior Beta(0.5,0.5); {DRAWS:,} Monte-Carlo draws for ranking/dominance.
  Wide intervals are the honest consequence of modest n and real-LLM sampling — that is the point of
  showing the posterior rather than a bare percentage. Same frozen pore + judge + worlds across all models.</div>
</div>'''


def build_md(res) -> str:
    o, w = [], lambda s="": o.append(s)
    w("# Model axis — posterior over the escalation region\n")
    w("> Beta-Binomial posterior (Jeffreys prior) over each proposer's escalation behaviour. "
      "Overlapping credible intervals ⇒ the apparent difference may be noise; separated ⇒ real.\n")
    names = {"escalation": "Escalation rate (all drift)",
             "high_drift": "High-drift escalation rate (drift ≥ 0.8)",
             "false_stop": "False-stop rate (reclaimable slack)"}
    for key, title in names.items():
        p = res[key]
        w(f"## {title}\n")
        w("| model | k/n | posterior mean | 95% CrI | P(highest) |")
        w("|---|---|---|---|---|")
        for r in p["table"]:
            ph = p["p_highest"][r["label"]]
            w(f"| {r['label']} | {r['k']}/{r['n']} | {r['mean']:.1%} | "
              f"[{r['ci95'][0]:.1%}, {r['ci95'][1]:.1%}] | {ph:.0%} |")
        w("")
    # a couple of headline dominance probabilities
    esc = res["escalation"]["dominance"]
    w("## Selected pairwise dominance (escalation rate)\n")
    top = sorted(esc.items(), key=lambda kv: -kv[1])[:6]
    for pair, prob in top:
        a, b = pair.split(">")
        w(f"- P({a} escalates more than {b}) = **{prob:.0%}**")
    w("")
    w("> Jeffreys prior Beta(0.5,0.5); 200k MC draws. Wide intervals are the honest consequence of "
      "modest n + real-LLM sampling — the reason to show a posterior, not a bare percentage.\n")
    return "\n".join(o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Posterior over proposer escalation behaviour.")
    ap.add_argument("--in-dir", default="artifacts/model_axis")
    ap.add_argument("--out", default="artifacts/model_axis/posterior.json")
    ap.add_argument("--md", default="docs/model-axis-posterior.md")
    ap.add_argument("--html", default="docs/model-axis-posterior.html")
    args = ap.parse_args(argv)

    in_dir = Path(args.in_dir)
    models = _load_models(in_dir)
    rng = np.random.default_rng(0)
    res = {
        "prior": "Jeffreys Beta(0.5,0.5)", "draws": DRAWS, "high_drift_threshold": HIGH_DRIFT,
        "escalation": _posterior(models, "esc", "n", rng),
        "high_drift": _posterior(models, "hi_k", "hi_n", rng),
        "false_stop": _posterior(models, "fs_k", "fs_n", rng),
    }
    Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    Path(args.md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.md).write_text(build_md(res), encoding="utf-8")
    Path(args.html).write_text(build_html(res), encoding="utf-8")

    print("=== Posterior escalation rate (mean, 95% CrI, P(highest)) ===")
    for r in res["escalation"]["table"]:
        ph = res["escalation"]["p_highest"][r["label"]]
        print(f"  {r['label']:14} {r['k']:>2}/{r['n']:<2}  {r['mean']:5.1%}  "
              f"[{r['ci95'][0]:5.1%},{r['ci95'][1]:5.1%}]  P(highest)={ph:4.0%}")
    print("\n=== False-stop rate (reclaimable slack) ===")
    for r in res["false_stop"]["table"]:
        print(f"  {r['label']:14} {r['k']:>2}/{r['n']:<2}  {r['mean']:5.1%}  "
              f"[{r['ci95'][0]:5.1%},{r['ci95'][1]:5.1%}]")
    d = res["escalation"]["dominance"]
    key = max(d, key=d.get)
    print(f"\n  most confident escalation ordering: P({key.replace('>',' > ')}) = {d[key]:.0%}")
    print(f"\nWrote -> {args.out}\nWrote -> {args.md}\nWrote -> {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
