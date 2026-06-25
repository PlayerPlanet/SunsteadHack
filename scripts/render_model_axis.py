#!/usr/bin/env python
"""Render the model-axis region overlay from artifacts/model_axis/regions.json.

One figure: escalation rate vs world-drift, one curve per proposer LLM. Same frozen
pore, same human judge, same worlds — so any separation between the curves is the
PROPOSER's doing. Emits docs/model-axis-region.{md,html}.

    python scripts/run_model_axis_region.py ...
    python scripts/render_model_axis.py
"""

import argparse
import json
import sys
from pathlib import Path

# A small categorical palette (ember family + cool tones) for the overlaid curves.
_COLORS = ["#e8732c", "#37a892", "#5b8dd9", "#d9a441", "#b86bd9", "#e0526b"]

HONESTY = (
    "The benchmark latency is modeled and the worlds (drift schedules) are fixed; only "
    "the proposer LLM varies, with the frozen pore and the human-proxy judge "
    "(claude-sonnet-4-6) held identical. So curve separation is attributable to the "
    "proposer's choices — which levers it reaches for as the world drifts — not to any "
    "change in the gate. This is the spatial escalation curve: a PROXY / lower bound of "
    "the legitimacy boundary, not the true epistemic edge. Per-model n is modest; read "
    "the trend, not the third digit."
)


def build_md(s: dict) -> str:
    cfg, models = s["config"], s["models"]
    o, w = [], lambda x="": o.append(x)
    w("# The model axis — how the proposer LLM moves the escalation region\n")
    w(f"> Frozen pore + frozen judge (`{cfg['human']}`) + identical worlds "
      f"(`{', '.join(cfg['styles'])}` × {cfg['iterations']}). **Only the optimizer LLM changes.** "
      "The region is where the agent leaves the zone it can act in unsupervised — escalation "
      "rate vs world-drift. If the curves separate, the backend model moved the boundary.\n")

    w("## The region (escalation rate vs drift)\n")
    w("```")
    w(_ascii_overlay(models))
    w("```\n")

    drifts = sorted({row["drift"] for m in models for row in m["spatial"]})
    w("| drift | " + " | ".join(m["label"] for m in models) + " |")
    w("|---|" + "---|" * len(models))
    for d in drifts:
        cells = []
        for m in models:
            hit = next((r for r in m["spatial"] if r["drift"] == d), None)
            cells.append(f"{hit['escalation_rate']:.0%}" if hit else "·")
        w(f"| {d:.2f} | " + " | ".join(cells) + " |")
    w("")

    w("## Overall escalation & false-stop rate\n")
    w("| proposer | model | escalation rate | escalations | false-stop rate |")
    w("|---|---|---|---|---|")
    for m in models:
        cg = m["calibration_gap"]
        w(f"| {m['label']} | `{m['model']}` | {m['escalation_rate']:.1%} | "
          f"{cg['n_escalated']} | {cg['false_stop_rate']:.1%} |")
    w("")
    w("**Reading it:** a higher curve / escalation rate means the proposer reaches for "
      "boundary-crossing levers (systemic GUCs, irreversible migrations) sooner as the world "
      "drifts — it leaves the unsupervised-action region earlier. The false-stop rate is how "
      "often the human waved those stops through: the slack a membrane could reclaim *for that "
      "proposer*. A model that escalates less but with a higher false-stop rate is being timid; "
      "one that escalates only when the human agrees is well-matched to the gate.\n")

    w("## Honesty caveat\n")
    w(f"> {HONESTY}\n")
    w("_Regenerate: `python scripts/run_model_axis_region.py --models all && python scripts/render_model_axis.py`._")
    return "\n".join(o)


def _ascii_overlay(models, width=40, height=12):
    drifts = sorted({row["drift"] for m in models for row in m["spatial"]})
    if not drifts:
        return "(no data)"
    dmin, dmax = drifts[0], drifts[-1]
    grid = [[" "] * width for _ in range(height)]
    marks = "ABCDEF"
    for mi, m in enumerate(models):
        for row in m["spatial"]:
            x = int((row["drift"] - dmin) / (dmax - dmin or 1) * (width - 1))
            y = int(row["escalation_rate"] * (height - 1))
            grid[height - 1 - y][x] = marks[mi % len(marks)]
    out = ["esc% 100|" + "".join(grid[0])]
    out += ["        |" + "".join(r) for r in grid[1:]]
    out.append("      0 +" + "-" * width)
    out.append(f"        drift {dmin:.2f}{' ' * (width - 10)}{dmax:.2f}")
    out.append("  legend: " + "  ".join(f"{marks[i]}={m['label']}" for i, m in enumerate(models)))
    return "\n".join(out)


def _svg_overlay(models, w=760, h=380):
    drifts = sorted({row["drift"] for m in models for row in m["spatial"]})
    dmin, dmax = (drifts[0], drifts[-1]) if drifts else (0.0, 1.0)
    pad_l, pad_r, pad_t, pad_b = 56, 160, 24, 48
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b

    def xy(d, rate):
        x = pad_l + ((d - dmin) / (dmax - dmin or 1)) * pw
        y = pad_t + ph - rate * ph
        return x, y

    grid = []
    for k in range(0, 101, 25):
        y = pad_t + ph - (k / 100) * ph
        grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + pw}" y2="{y:.1f}" class="grid"/>'
                    f'<text x="{pad_l - 8}" y="{y + 4:.1f}" class="ytick">{k}%</text>')
    series, legend = [], []
    for mi, m in enumerate(models):
        color = _COLORS[mi % len(_COLORS)]
        pts = " ".join(f"{xy(r['drift'], r['escalation_rate'])[0]:.1f},"
                       f"{xy(r['drift'], r['escalation_rate'])[1]:.1f}" for r in m["spatial"])
        series.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        ly = pad_t + 16 + mi * 22
        legend.append(f'<line x1="{pad_l + pw + 16}" y1="{ly}" x2="{pad_l + pw + 36}" y2="{ly}" '
                      f'stroke="{color}" stroke-width="3"/>'
                      f'<text x="{pad_l + pw + 42}" y="{ly + 4}" class="leg">{m["label"]} '
                      f'({m["escalation_rate"]:.0%})</text>')
    return f'''<svg viewBox="0 0 {w} {h}" role="img" aria-label="Escalation region vs drift per proposer LLM">
  {''.join(grid)}
  <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + ph}" class="axis"/>
  <line x1="{pad_l}" y1="{pad_t + ph}" x2="{pad_l + pw}" y2="{pad_t + ph}" class="axis"/>
  <text x="{pad_l + pw / 2}" y="{h - 8}" class="axlabel" text-anchor="middle">world-drift →</text>
  <text x="16" y="{pad_t + ph / 2}" class="axlabel" transform="rotate(-90 16 {pad_t + ph / 2})" text-anchor="middle">escalation rate</text>
  {''.join(series)}
  {''.join(legend)}
</svg>'''


def build_html(s: dict) -> str:
    cfg, models = s["config"], s["models"]
    rows = "".join(
        f"<tr><td class='mono'>{m['label']}</td><td class='mono muted'>{m['model']}</td>"
        f"<td class='mono'>{m['escalation_rate']:.1%}</td><td class='mono'>{m['calibration_gap']['n_escalated']}</td>"
        f"<td class='mono'>{m['calibration_gap']['false_stop_rate']:.1%}</td></tr>"
        for m in models
    )
    return f'''<title>Model axis — the proposer LLM and the escalation region</title>
<style>
  :root {{ --ground:#14171c; --panel:#1b1f27; --panel-2:#212732; --ink:#e9ebef; --muted:#8b94a3;
    --faint:#5b6573; --hair:#2a3039; --ember:#e8732c;
    --serif:Georgia,"Times New Roman",serif; --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,Menlo,monospace; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--ground); color:var(--ink); font-family:var(--sans); line-height:1.6; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:clamp(28px,5vw,72px) clamp(20px,4vw,48px); }}
  .mono {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }} .muted {{ color:var(--muted); }}
  .eyebrow {{ font-family:var(--mono); font-size:12px; letter-spacing:.22em; text-transform:uppercase; color:var(--ember); margin:0 0 22px; }}
  h1 {{ font-family:var(--serif); font-weight:400; font-size:clamp(28px,5vw,46px); line-height:1.1; margin:0 0 18px; }}
  h1 em {{ font-style:italic; color:var(--ember); }}
  h2 {{ font-family:var(--serif); font-weight:400; font-size:24px; margin:46px 0 14px; }}
  .lede {{ font-size:18px; color:var(--muted); max-width:64ch; }}
  .fig {{ background:var(--panel); border:1px solid var(--hair); border-radius:12px; padding:20px; margin:28px 0; overflow-x:auto; }}
  svg {{ width:100%; height:auto; min-width:600px; }}
  .grid {{ stroke:var(--hair); }} .axis {{ stroke:var(--faint); stroke-width:1.5; }}
  .ytick {{ fill:var(--muted); font:12px var(--mono); }} .axlabel {{ fill:var(--muted); font:13px var(--sans); }}
  .leg {{ fill:var(--ink); font:13px var(--sans); }}
  table {{ width:100%; border-collapse:collapse; margin:14px 0; font-size:14px; }}
  th,td {{ text-align:left; padding:8px 12px; border-bottom:1px solid var(--hair); }}
  th {{ color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
  .caveat {{ background:var(--panel-2); border-left:3px solid var(--ember); border-radius:0 8px 8px 0; padding:16px 20px; color:var(--muted); font-size:14px; margin:32px 0; }}
  p {{ max-width:68ch; }}
</style>
<div class="wrap">
  <p class="eyebrow">Boundary Instrument · model axis · shadow only</p>
  <h1>Change the proposer, <em>move the region</em>.</h1>
  <p class="lede">Frozen pore, frozen human-judge ({cfg['human']}), identical worlds — only the
  optimizer LLM changes. The escalation region is where the agent leaves the zone it can act in
  unsupervised. Where the curves separate, the backend model moved the boundary.</p>
  <div class="fig">{_svg_overlay(models)}</div>
  <h2>Overall escalation & false-stop rate</h2>
  <table><thead><tr><th>proposer</th><th>model</th><th>escalation rate</th><th>escalations</th><th>false-stop rate</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <div class="caveat">{HONESTY}</div>
</div>'''


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render the model-axis region overlay.")
    ap.add_argument("--in", dest="inp", default="artifacts/model_axis/regions.json")
    ap.add_argument("--md", default="docs/model-axis-region.md")
    ap.add_argument("--html", default="docs/model-axis-region.html")
    args = ap.parse_args(argv)

    s = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    Path(args.md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.md).write_text(build_md(s), encoding="utf-8")
    Path(args.html).write_text(build_html(s), encoding="utf-8")
    print(f"Wrote -> {args.md}\nWrote -> {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
