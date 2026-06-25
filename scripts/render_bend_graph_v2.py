#!/usr/bin/env python
"""Render the v2 deliverable from membrane_v2_eval.json: the generalization result
and the cost/risk Pareto frontier.

    python scripts/eval_membrane_v2.py
    python scripts/render_bend_graph_v2.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleanroom.membrane.taxonomy import _GUC_PROFILES  # noqa: E402

HONESTY = (
    "n is still 15. Trust the generalization *shape*, not the magnitudes. The risk "
    "taxonomy is domain priors from PostgreSQL docs, defined independent of the labels "
    "(see cleanroom/membrane/taxonomy.py) — the claim is *with a small fixed risk "
    "taxonomy the slack generalizes across levers*, not that the verdict is learned "
    "tabula rasa. Still shadow-only; the frozen pore made every real decision and is "
    "byte-for-byte unchanged. Giving the membrane the wheel and cross-domain transfer "
    "remain out of scope."
)


def build_md(ev: dict) -> str:
    dep, lo = ev["deployment_full_fit"], ev["held_out_lolo"]
    v2s, v1s, mq = lo["v2"]["summary"], lo["v1"]["summary"], lo["marquee"]
    fr = ev["pareto_frontier"]
    o, w = [], lambda s="": o.append(s)

    w("# Membrane v2 — semantic risk buys real cross-lever generalization\n")
    w("> v1 keyed on the lever *name*, so on a never-seen lever it abstained 100% — it "
      "memorized, it didn't generalize. v2 keys on the lever's *risk profile* "
      "(data-loss-on-crash, result-semantics, recoverability), so a never-seen lever "
      "inherits the verdict of its profile-peers. Same shadow discipline, same frozen ruler.\n")

    w("## The headline — held-out (leave-one-lever-out)\n")
    w("| | committed cold calls | correct | false-clears | reclaimed cold | abstention |")
    w("|---|---|---|---|---|---|")
    w(f"| **v2 (risk profile)** | {v2s['committed']} | {v2s['committed_correct']}/{v2s['committed']} | "
      f"{v2s['false_clears']} | {v2s['reclaimed_cold']} | {v2s['abstention_rate']:.0%} |")
    w(f"| v1 (lever identity) | {v1s['committed']} | — | {v1s['false_clears']} | "
      f"{v1s['reclaimed_cold']} | {v1s['abstention_rate']:.0%} |")
    w("")
    if mq:
        w(f"**Marquee:** hold out `fsync` *entirely* → v2 predicts **{mq['v2_cold_prediction']}** cold "
          f"(human verdict: {mq['true_human_verdict']}); v1 → **{mq['v1_cold_prediction']}**. "
          "v2 learned `data_loss_on_crash=HIGH → reject` from `full_page_writes` and applied it to a "
          "lever it had never seen. v1 had no precedent for the *name*.\n")
    w(f"v2 makes **{v2s['committed_correct']} correct cold calls with {v2s['false_clears']} false-clears** "
      f"on levers it never trained on; v1 makes **zero** committed calls there. That is the qualitative "
      "step — from memorization to generalization — and it is the result v1 structurally cannot produce.\n")

    w("## The Pareto frontier — reclaimed slack vs false-clear risk\n")
    w("v1 gave a single bend point. v2's decision is cost-theoretic — clear iff predicted "
      "`P(reject) < rho`, where `rho = C_human / C_false_clear` — so sweeping `rho` traces the whole "
      "tradeoff the operator can dial:\n")
    w("```")
    w(_ascii_frontier(fr))
    w("```")
    w("| rho | reclaimed | false-clears | remaining escalations |")
    w("|---|---|---|---|")
    for p in fr["points"]:
        w(f"| {p['rho']} | {p['reclaimed']} | {p['false_clears']} | {p['remaining_escalations']} |")
    w("")
    w(f"The **zero-false-clear knee sits at `rho ≤ 0.25`: reclaim 4, no false-clears** — exactly where "
      "v1's single point lives. Past `rho = 0.3` the operator can reclaim 8 by accepting the one "
      "`synchronous_commit` reject as a false-clear. \"Minimize false-clears\" stops being a magic "
      "threshold and becomes a risk dial.\n")

    w("## Deployment (full-fit, rho=0.25)\n")
    w(f"False-clears **{dep['false_clears']}**, reclaimed **{dep['reclaimed_false_stops']}**, "
      f"abstains on **{', '.join(dep['abstention_concentration']) or '—'}** (the bounded-tradeoff lever). "
      "Same honest headline as v1 — but now reached through risk semantics that generalize.\n")

    w("## The OOD abstain head\n")
    w("v2 abstains when it has no basis to stand behind a call — the manifesto's literal ask, now "
      "computable because the features are no longer degenerate:\n")
    w("| candidate | decision | why |")
    w("|---|---|---|")
    for name, d in ev["ood_demo"].items():
        w(f"| {name} | **{d['decision']}** | {d['reason']} |")
    w("")

    w("## The frozen risk taxonomy (domain priors, label-independent)\n")
    w("| lever | risk class | data-loss-on-crash | rationale |")
    w("|---|---|---|---|")
    levels = {0: "none", 1: "bounded", 2: "high"}
    for lv, p in _GUC_PROFILES.items():
        w(f"| `{lv}` | {p.risk_class} | {levels[p.data_loss_on_crash]} | {p.rationale} |")
    w("")

    w("## Honesty caveat\n")
    w(f"> {HONESTY}\n")
    w("_Regenerate: `python scripts/eval_membrane_v2.py && python scripts/render_bend_graph_v2.py`._")
    return "\n".join(o)


def _ascii_frontier(fr, width=44, height=10):
    pts = fr["points"]
    rmax = max(p["reclaimed"] for p in pts) or 1
    fmax = max(p["false_clears"] for p in pts) or 1
    grid = [[" "] * width for _ in range(height)]
    for p in pts:
        x = int(p["reclaimed"] / rmax * (width - 1))
        y = int(p["false_clears"] / fmax * (height - 1))
        grid[height - 1 - y][x] = "#"
    lines = [f"false-clears (0..{fmax})"]
    lines += ["".join(r) for r in grid]
    lines.append("0" + " " * (width - 18) + f"reclaimed (0..{rmax})")
    return "\n".join(lines)


def _svg_frontier(fr, w=720, h=340):
    pts = fr["points"]
    rmax = max(p["reclaimed"] for p in pts) or 1
    fmax = max(max(p["false_clears"] for p in pts), 1)
    pad_l, pad_r, pad_t, pad_b = 56, 40, 24, 48
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b

    def xy(reclaimed, fc):
        x = pad_l + (reclaimed / rmax) * pw
        y = pad_t + ph - (fc / fmax) * ph
        return x, y

    # de-dup frontier points (many rho map to same (reclaimed, fc))
    seen, line = set(), []
    for p in sorted(pts, key=lambda p: (p["reclaimed"], p["false_clears"])):
        k = (p["reclaimed"], p["false_clears"])
        if k in seen:
            continue
        seen.add(k)
        line.append(k)
    poly = " ".join(f"{xy(r, f)[0]:.1f},{xy(r, f)[1]:.1f}" for r, f in line)
    dots = "".join(
        f'<circle cx="{xy(r, f)[0]:.1f}" cy="{xy(r, f)[1]:.1f}" r="4" class="pt"/>'
        for r, f in line
    )
    vx, vy = xy(4, 0)  # v1's knee
    grid = []
    for k in range(fmax + 1):
        y = pad_t + ph - (k / fmax) * ph
        grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + pw}" y2="{y:.1f}" class="grid"/>'
                    f'<text x="{pad_l - 8}" y="{y + 4:.1f}" class="ytick">{k}</text>')
    return f'''<svg viewBox="0 0 {w} {h}" role="img" aria-label="Pareto frontier: reclaimed slack vs false-clears">
  {''.join(grid)}
  <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + ph}" class="axis"/>
  <line x1="{pad_l}" y1="{pad_t + ph}" x2="{pad_l + pw}" y2="{pad_t + ph}" class="axis"/>
  <text x="{pad_l + pw / 2}" y="{h - 8}" class="axlabel" text-anchor="middle">false-stops reclaimed →</text>
  <text x="16" y="{pad_t + ph / 2}" class="axlabel" transform="rotate(-90 16 {pad_t + ph / 2})" text-anchor="middle">← false-clears (cost)</text>
  <polyline points="{poly}" class="frontier"/>
  {dots}
  <circle cx="{vx:.1f}" cy="{vy:.1f}" r="6" class="knee"/>
  <text x="{vx + 12:.1f}" y="{vy - 8:.1f}" class="lbl knee-t">v1 knee — 4 reclaimed, 0 false-clears (rho≤0.25)</text>
</svg>'''


def build_html(ev: dict) -> str:
    dep, lo = ev["deployment_full_fit"], ev["held_out_lolo"]
    v2s, v1s, mq = lo["v2"]["summary"], lo["v1"]["summary"], lo["marquee"]
    fr = ev["pareto_frontier"]
    levels = {0: "none", 1: "bounded", 2: "high"}
    tax = "".join(
        f"<tr><td class='mono'>{lv}</td><td>{p.risk_class}</td>"
        f"<td class='dl-{levels[p.data_loss_on_crash]}'>{levels[p.data_loss_on_crash]}</td>"
        f"<td class='muted'>{p.rationale}</td></tr>"
        for lv, p in _GUC_PROFILES.items()
    )
    ood = "".join(
        f"<tr><td class='mono'>{n}</td><td class='dec-abstain'>{d['decision']}</td>"
        f"<td class='mono muted'>{d['reason']}</td></tr>"
        for n, d in ev["ood_demo"].items()
    )
    return f'''<title>Membrane v2 — generalization & the cost/risk frontier</title>
<style>
  :root {{
    --ground:#14171c; --panel:#1b1f27; --panel-2:#212732; --ink:#e9ebef; --muted:#8b94a3;
    --faint:#5b6573; --hair:#2a3039; --ember:#e8732c; --approve:#37a892; --reject:#e0526b;
    --abstain:#d9a441;
    --serif:Georgia,"Times New Roman",serif; --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,Menlo,monospace;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--ground); color:var(--ink); font-family:var(--sans); line-height:1.6; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:clamp(28px,5vw,72px) clamp(20px,4vw,48px); }}
  .mono {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }} .muted {{ color:var(--muted); }}
  .eyebrow {{ font-family:var(--mono); font-size:12px; letter-spacing:.22em; text-transform:uppercase; color:var(--ember); margin:0 0 22px; }}
  h1 {{ font-family:var(--serif); font-weight:400; text-wrap:balance; font-size:clamp(28px,5vw,46px); line-height:1.1; margin:0 0 18px; letter-spacing:-.01em; }}
  h1 em {{ font-style:italic; color:var(--ember); }}
  h2 {{ font-family:var(--serif); font-weight:400; font-size:24px; margin:48px 0 14px; }}
  .lede {{ font-size:18px; color:var(--muted); max-width:64ch; }}
  .fig {{ background:var(--panel); border:1px solid var(--hair); border-radius:12px; padding:20px; margin:28px 0; overflow-x:auto; }}
  svg {{ width:100%; height:auto; min-width:560px; }}
  .grid {{ stroke:var(--hair); }} .axis {{ stroke:var(--faint); stroke-width:1.5; }}
  .ytick {{ fill:var(--muted); font:12px var(--mono); }} .axlabel {{ fill:var(--muted); font:13px var(--sans); }}
  .frontier {{ fill:none; stroke:var(--ember); stroke-width:2.5; }}
  .pt {{ fill:var(--ember); }} .knee {{ fill:var(--approve); }} .lbl {{ font:12px var(--sans); }} .knee-t {{ fill:var(--approve); }}
  table {{ width:100%; border-collapse:collapse; margin:14px 0; font-size:14px; }}
  th,td {{ text-align:left; padding:8px 12px; border-bottom:1px solid var(--hair); vertical-align:top; }}
  th {{ color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
  .win {{ color:var(--approve); font-weight:600; }} .dec-abstain {{ color:var(--abstain); font-weight:600; }}
  .dl-high {{ color:var(--reject); }} .dl-bounded {{ color:var(--abstain); }} .dl-none {{ color:var(--approve); }}
  .stats {{ display:flex; gap:14px; flex-wrap:wrap; margin:22px 0; }}
  .stat {{ background:var(--panel); border:1px solid var(--hair); border-radius:10px; padding:14px 18px; flex:1; min-width:150px; }}
  .stat .n {{ font-family:var(--serif); font-size:30px; display:block; }} .stat .k {{ color:var(--muted); font-size:13px; }}
  .caveat {{ background:var(--panel-2); border-left:3px solid var(--ember); border-radius:0 8px 8px 0; padding:16px 20px; color:var(--muted); font-size:14px; margin:32px 0; }}
  p {{ max-width:68ch; }} code {{ font-family:var(--mono); background:var(--panel-2); padding:1px 5px; border-radius:4px; }}
</style>
<div class="wrap">
  <p class="eyebrow">Boundary Instrument · Membrane v2 · shadow only</p>
  <h1>From memorizing names to <em>generalizing risk</em>.</h1>
  <p class="lede">v1 keyed on the lever name and abstained on everything it hadn't seen. v2 keys on the
  lever's <em>risk profile</em>, so a never-before-seen lever inherits the verdict of its profile-peers —
  real cross-lever generalization, still measured against the unchanged frozen ruler.</p>

  <div class="stats">
    <div class="stat"><span class="n win">{v2s['committed_correct']}/{v2s['committed']}</span><span class="k">correct cold calls on held-out levers</span></div>
    <div class="stat"><span class="n">{v1s['committed']}</span><span class="k">cold calls v1 could make (it abstains)</span></div>
    <div class="stat"><span class="n win">{v2s['false_clears']}</span><span class="k">held-out false-clears</span></div>
    <div class="stat"><span class="n">{v2s['abstention_rate']:.0%}</span><span class="k">v2 abstention (was 100% in v1)</span></div>
  </div>

  <h2>The marquee</h2>
  <p>Hold out <code>fsync</code> <strong>entirely</strong> → v2 predicts <strong class="win">{mq['v2_cold_prediction']}</strong>
  cold (human verdict: {mq['true_human_verdict']}); v1 → <strong>{mq['v1_cold_prediction']}</strong>. v2 learned
  <code>data_loss_on_crash=HIGH → reject</code> from <code>full_page_writes</code> and applied it to a lever it had
  never seen. That is the qualitative step v1 structurally cannot take.</p>

  <h2>The cost / risk frontier</h2>
  <p>v2's decision is cost-theoretic: clear iff predicted <code>P(reject) &lt; rho</code>, where
  <code>rho = C_human / C_false_clear</code>. Sweeping <code>rho</code> traces the whole tradeoff. The
  zero-false-clear knee sits exactly where v1's single point lived — past it, the operator can dial up
  reclaimed slack by accepting the one ambiguous reject.</p>
  <div class="fig">{_svg_frontier(fr)}</div>

  <h2>The OOD abstain head</h2>
  <p>v2 abstains when it has no basis to stand behind a call — now computable because the features are no
  longer degenerate.</p>
  <table><thead><tr><th>candidate</th><th>decision</th><th>why</th></tr></thead><tbody>{ood}</tbody></table>

  <h2>The frozen risk taxonomy</h2>
  <p>Domain priors from documented PostgreSQL behaviour, defined <em>independent of the labels</em>. This is
  the honesty boundary: the claim is that <em>with</em> such priors the slack generalizes, not that it is
  learned from 15 rows.</p>
  <table><thead><tr><th>lever</th><th>risk class</th><th>data-loss-on-crash</th><th>rationale</th></tr></thead>
  <tbody>{tax}</tbody></table>

  <div class="caveat">{HONESTY}</div>
</div>'''


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render the membrane v2 deliverable.")
    ap.add_argument("--eval", default="artifacts/deep_probe/membrane_v2_eval.json")
    ap.add_argument("--md", default="docs/bend-graph-v2.md")
    ap.add_argument("--html", default="docs/bend-graph-v2.html")
    args = ap.parse_args(argv)

    ev = json.loads(Path(args.eval).read_text(encoding="utf-8"))
    Path(args.md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.md).write_text(build_md(ev), encoding="utf-8")
    Path(args.html).write_text(build_html(ev), encoding="utf-8")
    print(f"Wrote -> {args.md}")
    print(f"Wrote -> {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
