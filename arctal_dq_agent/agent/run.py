"""CLI: scan the dataset, write the two output channels, print the cost funnel.

  python -m agent                 # Tier 0 + trail, no API key (deterministic)
  python -m agent --llm           # + Tier 1 reasoning (needs ANTHROPIC_API_KEY)

Writes `findings.jsonl` (machine) and `REPORT.md` (human) into --out (default
./out). The two channels are a deliberate split: tools consume the JSONL; a domain
expert triages the Markdown. See README, "Two output channels".
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .data import build_context, data_dir, load_tables
from .finding import SEVERITY_RANK
from .reasoning import make_reasoner
from .review import assess_record

# Cost assumptions (USD per 1M tokens). Clearly labelled so they are easy to update;
# the token *counts* are measured from the run, only these unit prices are assumed.
PRICE = {
    "claude-haiku-4-5": (1.00, 5.00),    # (input, output)
    "claude-sonnet-4-6": (3.00, 15.00),
}
SCALE_TARGET = 30_000


def _scan(tables, ctx, reasoner):
    findings, tier1_rows = [], 0
    grain = {"issuances": "isin", "impacts": "isin", "cat_allocations": "isin"}
    for table in grain:
        for row in tables[table]:
            fs = assess_record(table, row, ctx, reasoner)
            findings += fs
            if table in ("impacts", "cat_allocations") and any(f.tier == "llm" for f in fs):
                tier1_rows += 1
    return findings, tier1_rows


def _write_jsonl(findings, path: Path):
    with open(path, "w", encoding="utf-8") as fh:
        for f in findings:
            fh.write(json.dumps(f.to_json(), ensure_ascii=False) + "\n")


def _row(f):
    why = f.rationale.replace("|", "/").strip()
    pc = "" if f.proposed_correction is None else f"`{f.proposed_correction}`"
    return f"| {f.severity} | `{f.isin}` | {f.field} | {f.check_id} | {why} | {pc} |"


def _section(title, blurb, items):
    items = sorted(items, key=lambda f: (-SEVERITY_RANK[f.severity], -f.confidence))
    lines = [f"## {title} ({len(items)})", "", f"_{blurb}_", ""]
    if not items:
        lines += ["_none._", ""]
        return lines
    lines += ["| sev | isin | field | check | why | proposed |",
              "|-----|------|-------|-------|-----|----------|"]
    lines += [_row(f) for f in items]
    lines.append("")
    return lines


def _write_report(findings, path: Path, meta: dict):
    by_disp = {d: [f for f in findings if f.disposition == d]
               for d in ("auto_correct", "flag", "escalate")}
    from collections import Counter
    by_check = Counter(f.check_id for f in findings)
    by_table = Counter(f.table for f in findings)

    L = [
        "# Green-bond data-quality findings",
        "",
        f"_{meta['bonds']} bonds · {meta['rows']:,} rows scanned · {len(findings)} findings · "
        f"mode: **{meta['mode']}** · {meta['date']}_",
        "",
        "**How to read this.** Three buckets by what *you* need to do:",
        "",
        f"- **Auto-correct ({len(by_disp['auto_correct'])})** — recomputed exactly from other "
        "stored values; apply or spot-check.",
        f"- **Flag ({len(by_disp['flag'])})** — a real inconsistency whose *fix* is debatable; "
        "needs a human call.",
        f"- **Escalate ({len(by_disp['escalate'])})** — only the source PDF settles it; the agent "
        "abstained on purpose.",
        "",
        "Per-finding evidence (the conflicting numbers, trail excerpts) lives in "
        "`findings.jsonl` for tooling — this page stays one line per finding.",
        "",
    ]
    L += _section("Auto-correct — objective fixes", "Recomputed from primitives; the value is determined.",
                  by_disp["auto_correct"])
    L += _section("Flag — needs a human call", "Inconsistent, but which side is wrong is a judgment.",
                  by_disp["flag"])
    L += _section("Escalate — open the source PDF", "Ambiguous or unverifiable from extracted data alone.",
                  by_disp["escalate"])
    L += ["## Rollup", "", "**By check:** " + ", ".join(f"{k} ({v})" for k, v in by_check.most_common()),
          "", "**By table:** " + ", ".join(f"{k} ({v})" for k, v in by_table.most_common()), ""]
    path.write_text("\n".join(L), encoding="utf-8")


def _cost_note(meta, reasoner) -> list[str]:
    s = reasoner.stats
    calls = s.haiku_calls + s.sonnet_calls
    # measured cost from real token usage, if any
    cost = 0.0
    if s.input_tokens or s.output_tokens:
        hi, ho = PRICE["claude-haiku-4-5"]
        si, so = PRICE["claude-sonnet-4-6"]
        # attribute tokens proportionally to call counts (good enough for an estimate)
        if calls:
            h_frac = s.haiku_calls / calls
            cost = ((s.input_tokens * h_frac) * hi + (s.input_tokens * (1 - h_frac)) * si
                    + (s.output_tokens * h_frac) * ho + (s.output_tokens * (1 - h_frac)) * so) / 1e6
    lines = [
        f"  rows scanned:        {meta['rows']:,}",
        f"  Tier-1 (LLM) rows:   {meta['tier1_rows']}  ({meta['tier1_rows']/max(meta['rows'],1)*100:.1f}% of rows)",
        f"  LLM calls:           {calls}  (haiku {s.haiku_calls}, sonnet {s.sonnet_calls})",
    ]
    if cost:
        per_bond = cost / max(meta["bonds"], 1)
        lines += [
            f"  measured LLM cost:   ${cost:.4f}  (${per_bond*1000:.2f} / 1k bonds)",
            f"  extrapolated 30k:    ${per_bond*SCALE_TARGET:.2f}  (Tier-1 ratio held constant)",
        ]
    else:
        lines.append("  LLM cost:            $0 (deterministic mode — Tier 0 + trail only)")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agent", description="Green-bond data-quality agent")
    ap.add_argument("--llm", action="store_true", help="enable Tier-1 LLM reasoning (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--out", default="out", help="output directory (default: ./out)")
    args = ap.parse_args(argv)

    t0 = time.time()
    tables = load_tables()
    ctx = build_context(tables)
    reasoner = make_reasoner(args.llm)
    mode = "Tier 0+1 (deterministic + LLM)" if reasoner.enabled else "Tier 0 (deterministic, no API key)"

    if reasoner.enabled:
        from .reasoning import triage_category, triage_impact
        n_imp = sum(1 for r in tables["impacts"] if triage_impact(r, ctx))
        n_cat = sum(1 for r in tables["cat_allocations"] if triage_category(r, ctx))
        print(f"tier-1: ~{n_imp + n_cat} rows to reason over (impacts {n_imp}, categories {n_cat}); "
              f"haiku first, sonnet on low confidence — this takes a few minutes...", file=sys.stderr)

    findings, tier1_rows = _scan(tables, ctx, reasoner)
    if reasoner.enabled and sys.stderr.isatty():
        print(file=sys.stderr)  # finalize the in-place heartbeat line

    rows = sum(len(tables[t]) for t in ("issuances", "impacts", "cat_allocations"))
    meta = {"bonds": len(tables["issuances"]), "rows": rows, "tier1_rows": tier1_rows,
            "mode": mode, "date": time.strftime("%Y-%m-%d")}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    _write_jsonl(findings, out / "findings.jsonl")
    _write_report(findings, out / "REPORT.md", meta)

    print(f"data: {data_dir()}")
    print(f"mode: {mode}")
    print(f"{len(findings)} findings over {rows:,} rows in {time.time()-t0:.2f}s "
          f"-> {out/'findings.jsonl'}, {out/'REPORT.md'}")
    print("cost funnel:")
    for line in _cost_note(meta, reasoner):
        print(line)


if __name__ == "__main__":
    main()
