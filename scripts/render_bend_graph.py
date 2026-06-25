#!/usr/bin/env python
"""Render the bend graph (issue #20 deliverable) from membrane_eval.json.

Emits docs/bend-graph.md and docs/bend-graph.html: two longitudinal curves on the
same axis, same held-out judge, same data — the frozen pore (flat by design) vs the
membrane-shadow (bent down by the clean-precedent slack it reclaims). The membrane
never acted, so the bend is measured *against* the frozen ruler, not produced by
moving it.

    python scripts/eval_membrane.py        # produces artifacts/deep_probe/membrane_eval.json
    python scripts/render_bend_graph.py
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HONESTY = (
    "This is a **shadow** measurement of learnability under held-out drift — not a "
    "deployed self-aware agent, and not cross-domain. The membrane never acted; the "
    "frozen pore (`cleanroom/pore`) made every real decision and is byte-for-byte "
    "unchanged. Latency is modeled (live p99 proven separately). The held-out split "
    "is leave-one-lever-out, not held-out-regime: the frozen pore concentrates 100% "
    "of escalations in the `regime_break` tier, so a held-out-regime split has zero "
    "training labels — leave-one-lever-out is the honest, stricter analogue."
)


def build_md(ev: dict) -> str:
    dep = ev["deployment_full_fit"]
    ho = ev["held_out_leave_one_lever_out"]
    ip = ev["in_precedent_loo"]
    bd = ev["bend"]
    o, w = [], lambda s="": o.append(s)

    w("# The bend graph — the learned membrane, in shadow, against a frozen ruler\n")
    w("> **Issue #20.** Deploy the learned membrane as a SHADOW gate — it logs what it "
      "*would* decide but never touches the wheel — and show the longitudinal escalation "
      "curve bend down *without moving the frozen ruler.*\n")

    w("## The figure\n")
    w("```")
    w(_ascii_bend(bd))
    w("```")
    w(f"Frozen pore raises **{bd['frozen_total']}** escalations over {ev['n_rows']} steps. "
      f"The membrane-shadow would wave through **{bd['frozen_total'] - bd['membrane_total']}** of "
      f"them (clean-precedent false stops), leaving **{bd['membrane_total']}** — a "
      f"**{bd['reduction_pct']}% reduction** in human escalations, with **zero false-clears**. "
      "Abstentions and escalates still count as escalations, so the bend is bounded by exactly "
      "the slack the membrane can stand behind.\n")

    w("## What the membrane decided (full-fit deployment gate)\n")
    w("| lever | membrane | P(approve) | human verdicts |")
    w("|---|---|---|---|")
    for lv, d in sorted(dep["by_lever"].items(), key=lambda kv: kv[1]["decision"]):
        verds = ", ".join(f"{k}×{v}" for k, v in d["true"].items())
        w(f"| `{lv}` | **{d['decision']}** | {d['p_approve']} | {verds} |")
    w("")
    w(f"- **False-clear rate: {dep['false_clear_rate']:.0%}** ({dep['false_clears']}/{dep['n']}) — "
      "the dangerous error (auto-clearing a human-reject) never happens: a lever with *any* "
      "reject in its record is never auto-cleared.")
    w(f"- **Reclaimed false-stops: {dep['reclaimed_false_stops']}** — clean-precedent stops the "
      "membrane would wave through (the bend).")
    w(f"- **Abstention concentrates on `{', '.join(dep['abstention_concentration'])}`** — the one "
      "lever that drew opposite human verdicts. The membrane refuses to call the irreducible "
      "judgment and asks a human, exactly as a calibrated agent should.\n")

    w("## The honesty guardrail — held-out (leave-one-lever-out)\n")
    w(f"On a lever it has **never seen**, the membrane abstains **{ho['abstention_rate']:.0%}** of the "
      f"time and auto-clears **nothing** (false-clear rate **{ho['false_clear_rate']:.0%}**). "
      "It does not hallucinate generalization: confronted with a novel lever it asks a human "
      "rather than guessing. This is the abstain head working, and it is why the bend only "
      "appears for levers with precedent.\n")

    w("## Calibration / robustness (leave-one-out on n=15)\n")
    w(f"- Expected calibration error (ECE): **{ip['calibration']['ece']}** "
      f"({ip['calibration']['note']}).")
    w(f"- The single LOO error is **1 false-clear** — the lone `synchronous_commit` reject, "
      "which when held out leaves that lever looking pure-approve. This is the published 93.3% "
      "residual, and it is *precisely why* the deployment gate (which sees the reject) abstains "
      "on `synchronous_commit`: erring toward asking turns the one irreducible case into an "
      "abstention instead of a dangerous clear.\n")
    w("| P(approve) bin | n | mean P(approve) | observed approve rate |")
    w("|---|---|---|---|")
    for row in ip["calibration"]["reliability"]:
        w(f"| {row['bin']} | {row['n']} | {row['mean_p_approve']} | {row['observed_approve_rate']} |")
    w("")

    w("## Honesty caveat\n")
    w(f"> {HONESTY}\n")
    w("_Regenerate: `python scripts/eval_membrane.py && python scripts/render_bend_graph.py`._")
    return "\n".join(o)


def _ascii_bend(bd: dict, width: int = 56, height: int = 12) -> str:
    """A compact ASCII rendering of the two cumulative-escalation curves."""
    work = bd["work"]
    fz = bd["frozen_cumulative_escalations"]
    mb = bd["membrane_cumulative_escalations"]
    n = len(work)
    ymax = max(fz[-1], 1)
    grid = [[" "] * width for _ in range(height)]

    def plot(series, ch):
        for x in range(width):
            i = min(n - 1, int(x / max(1, width - 1) * (n - 1)))
            y = int((series[i] / ymax) * (height - 1))
            grid[height - 1 - y][x] = ch

    plot(fz, "·")       # frozen (upper)
    plot(mb, "#")       # membrane-shadow (lower where it bends)
    lines = ["".join(r) for r in grid]
    out = [f"escalations (0..{ymax})  · frozen   # membrane-shadow"]
    out += lines
    out.append("0" + " " * (width - 12) + f"work ({n} steps)")
    return "\n".join(out)


def _svg_bend(bd: dict, w: int = 760, h: int = 320) -> str:
    work, fz, mb = bd["work"], bd["frozen_cumulative_escalations"], bd["membrane_cumulative_escalations"]
    n = len(work)
    ymax = max(fz[-1], 1)
    pad_l, pad_r, pad_t, pad_b = 52, 150, 24, 40
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b

    def pt(i, val):
        x = pad_l + (i / max(1, n - 1)) * pw
        y = pad_t + ph - (val / ymax) * ph
        return f"{x:.1f},{y:.1f}"

    fz_path = " ".join(pt(i, v) for i, v in enumerate(fz))
    mb_path = " ".join(pt(i, v) for i, v in enumerate(mb))
    # y gridlines
    grid = []
    for k in range(0, ymax + 1, max(1, ymax // 5)):
        y = pad_t + ph - (k / ymax) * ph
        grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + pw}" y2="{y:.1f}" class="grid"/>'
                    f'<text x="{pad_l - 8}" y="{y + 4:.1f}" class="ytick">{k}</text>')
    reclaimed = bd["frozen_total"] - bd["membrane_total"]
    end_fz = pt(n - 1, fz[-1]).split(",")
    end_mb = pt(n - 1, mb[-1]).split(",")
    return f'''<svg viewBox="0 0 {w} {h}" role="img" aria-label="Bend graph: frozen vs membrane-shadow cumulative escalations">
  {''.join(grid)}
  <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + ph}" class="axis"/>
  <line x1="{pad_l}" y1="{pad_t + ph}" x2="{pad_l + pw}" y2="{pad_t + ph}" class="axis"/>
  <text x="{pad_l + pw / 2}" y="{h - 6}" class="axlabel" text-anchor="middle">cumulative work ({n} optimizer steps)</text>
  <polyline points="{fz_path}" class="frozen"/>
  <polyline points="{mb_path}" class="membrane"/>
  <circle cx="{end_fz[0]}" cy="{end_fz[1]}" r="4" class="dot-frozen"/>
  <circle cx="{end_mb[0]}" cy="{end_mb[1]}" r="4" class="dot-membrane"/>
  <text x="{float(end_fz[0]) + 10}" y="{float(end_fz[1]) + 4}" class="lbl frozen-t">frozen pore — {bd['frozen_total']} escalations</text>
  <text x="{float(end_mb[0]) + 10}" y="{float(end_mb[1]) + 4}" class="lbl membrane-t">membrane-shadow — {bd['membrane_total']}</text>
  <text x="{float(end_mb[0]) + 10}" y="{float(end_mb[1]) + 22}" class="lbl reclaim-t">↑ {reclaimed} reclaimed · 0 false-clears</text>
</svg>'''


def build_html(ev: dict) -> str:
    dep, ho, ip, bd = (ev["deployment_full_fit"], ev["held_out_leave_one_lever_out"],
                       ev["in_precedent_loo"], ev["bend"])
    rows = "".join(
        f"<tr><td class='mono'>{lv}</td><td class='dec dec-{d['decision']}'>{d['decision']}</td>"
        f"<td class='mono'>{d['p_approve']}</td>"
        f"<td class='mono muted'>{', '.join(f'{k}×{v}' for k, v in d['true'].items())}</td></tr>"
        for lv, d in sorted(dep["by_lever"].items(), key=lambda kv: kv[1]["decision"])
    )
    rel = "".join(
        f"<tr><td class='mono'>{r['bin']}</td><td class='mono'>{r['n']}</td>"
        f"<td class='mono'>{r['mean_p_approve']}</td><td class='mono'>{r['observed_approve_rate']}</td></tr>"
        for r in ip["calibration"]["reliability"]
    )
    return f'''<title>The bend graph — the learned membrane in shadow</title>
<style>
  :root {{
    --ground:#14171c; --panel:#1b1f27; --panel-2:#212732; --ink:#e9ebef; --muted:#8b94a3;
    --faint:#5b6573; --hair:#2a3039; --ember:#e8732c; --approve:#37a892; --reject:#e0526b;
    --abstain:#d9a441; --calm:#3c4452;
    --serif:Georgia,"Times New Roman",serif; --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,Menlo,monospace;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--ground); color:var(--ink); font-family:var(--sans); line-height:1.6; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:clamp(28px,5vw,72px) clamp(20px,4vw,48px); }}
  .mono {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }}
  .muted {{ color:var(--muted); }}
  .eyebrow {{ font-family:var(--mono); font-size:12px; letter-spacing:.22em; text-transform:uppercase; color:var(--ember); margin:0 0 22px; }}
  h1 {{ font-family:var(--serif); font-weight:400; text-wrap:balance; font-size:clamp(28px,5vw,48px); line-height:1.1; margin:0 0 18px; letter-spacing:-.01em; }}
  h1 em {{ font-style:italic; color:var(--ember); }}
  h2 {{ font-family:var(--serif); font-weight:400; font-size:24px; margin:48px 0 14px; }}
  .lede {{ font-size:18px; color:var(--muted); max-width:62ch; margin:0 0 8px; }}
  .fig {{ background:var(--panel); border:1px solid var(--hair); border-radius:12px; padding:20px; margin:28px 0; overflow-x:auto; }}
  svg {{ width:100%; height:auto; min-width:560px; }}
  .grid {{ stroke:var(--hair); stroke-width:1; }}
  .axis {{ stroke:var(--faint); stroke-width:1.5; }}
  .ytick,.axlabel {{ fill:var(--muted); font:12px var(--mono); }} .axlabel {{ font-family:var(--sans); }}
  .frozen {{ fill:none; stroke:var(--calm); stroke-width:2.5; }}
  .membrane {{ fill:none; stroke:var(--ember); stroke-width:2.5; }}
  .dot-frozen {{ fill:var(--calm); }} .dot-membrane {{ fill:var(--ember); }}
  .lbl {{ font:13px var(--sans); }} .frozen-t {{ fill:var(--muted); }} .membrane-t {{ fill:var(--ember); }}
  .reclaim-t {{ fill:var(--approve); font:12px var(--mono); }}
  .stats {{ display:flex; gap:14px; flex-wrap:wrap; margin:22px 0; }}
  .stat {{ background:var(--panel); border:1px solid var(--hair); border-radius:10px; padding:14px 18px; flex:1; min-width:150px; }}
  .stat .n {{ font-family:var(--serif); font-size:30px; display:block; }}
  .stat .k {{ color:var(--muted); font-size:13px; }}
  .good {{ color:var(--approve); }} .warn {{ color:var(--abstain); }}
  table {{ width:100%; border-collapse:collapse; margin:14px 0; font-size:14px; }}
  th,td {{ text-align:left; padding:8px 12px; border-bottom:1px solid var(--hair); }}
  th {{ color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
  .dec {{ font-weight:600; }} .dec-auto_clear {{ color:var(--approve); }} .dec-escalate {{ color:var(--reject); }} .dec-abstain {{ color:var(--abstain); }}
  .caveat {{ background:var(--panel-2); border-left:3px solid var(--ember); border-radius:0 8px 8px 0; padding:16px 20px; color:var(--muted); font-size:14px; margin:32px 0; }}
  p {{ max-width:68ch; }}
</style>
<div class="wrap">
  <p class="eyebrow">Boundary Instrument · Issue #20 · shadow only</p>
  <h1>The curve <em>bends</em> — without moving the frozen ruler.</h1>
  <p class="lede">The learned membrane is deployed as a <em>shadow</em> gate: it logs what it would
  decide, but the frozen pore makes every real call. The escalation curve bends down by exactly
  the slack the membrane can stand behind — measured against the ruler, not produced by moving it.</p>

  <div class="fig">{_svg_bend(bd)}</div>

  <div class="stats">
    <div class="stat"><span class="n">{bd['reduction_pct']}%</span><span class="k">fewer escalations (shadow)</span></div>
    <div class="stat"><span class="n good">{dep['false_clears']}</span><span class="k">false-clears — the dangerous error</span></div>
    <div class="stat"><span class="n">{dep['reclaimed_false_stops']}</span><span class="k">false-stops reclaimed</span></div>
    <div class="stat"><span class="n warn">{sum(dep['abstention_concentration'].values())}</span><span class="k">abstentions (the irreducible lever)</span></div>
  </div>

  <h2>What the membrane decided</h2>
  <p>Full-fit deployment gate over every escalation. A lever with <em>any</em> reject in its record is
  never auto-cleared — that is why the false-clear rate is structurally zero. Abstention lands on
  <span class="mono">synchronous_commit</span>, the one lever that drew opposite human verdicts.</p>
  <table><thead><tr><th>lever</th><th>membrane</th><th>P(approve)</th><th>human verdicts</th></tr></thead>
  <tbody>{rows}</tbody></table>

  <h2>The honesty guardrail — held-out (leave-one-lever-out)</h2>
  <p>On a lever it has <strong>never seen</strong>, the membrane abstains
  <strong>{ho['abstention_rate']:.0%}</strong> of the time and auto-clears <strong>nothing</strong>
  (false-clear rate <span class="good">{ho['false_clear_rate']:.0%}</span>). It does not hallucinate
  generalization — confronted with a novel lever it asks a human. The bend only appears for levers
  with precedent; that is the abstain head working.</p>

  <h2>Calibration / robustness (leave-one-out, n=15)</h2>
  <p>ECE <span class="mono">{ip['calibration']['ece']}</span> ({ip['calibration']['note']}). The single
  LOO error is one false-clear — the lone <span class="mono">synchronous_commit</span> reject, which
  when held out leaves the lever looking pure-approve. That is the published 93.3% residual, and it is
  exactly why the deployment gate (which <em>sees</em> the reject) abstains there.</p>
  <table><thead><tr><th>P(approve) bin</th><th>n</th><th>mean P(approve)</th><th>observed approve rate</th></tr></thead>
  <tbody>{rel}</tbody></table>

  <div class="caveat">{HONESTY}</div>
</div>'''


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render the bend graph from membrane_eval.json.")
    ap.add_argument("--eval", default="artifacts/deep_probe/membrane_eval.json")
    ap.add_argument("--md", default="docs/bend-graph.md")
    ap.add_argument("--html", default="docs/bend-graph.html")
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
