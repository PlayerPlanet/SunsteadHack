"""Run the instrument end-to-end and print the trustworthy-region curves.

    python -m bonds_instrument            # deterministic agents, no API key
    python -m bonds_instrument --llm      # also run the LLM agent (needs ANTHROPIC_API_KEY)

Writes artifacts/bonds/findings.jsonl and artifacts/bonds/REGIONS.md.
"""

import argparse
import importlib.util
import json
import os
import sys
from collections import Counter
from pathlib import Path

from . import instrument
from .agents import JudgeOnlyAgent, LLMAgent, StationarityAgent
from .claims import build_clean_claims, poison
from .data import DRIFT_BINS

_BINKEYS = [f"{lo:.1f}-{min(hi,1.0):.1f}" for lo, hi in DRIFT_BINS]


def _bar(x: float, width: int = 20) -> str:
    return "#" * int(round(x * width))


def print_curve(name: str, bins) -> None:
    print(f"\n=== {name} — trustworthy-region curve ===")
    print(f"  {'drift':9} {'n':>4}  {'escalate':>8}  {'false-clr':>9}  {'over-ask':>8}  {'just-ask':>8}")
    for k in _BINKEYS:
        s = bins[k]
        if s.n == 0:
            continue
        print(f"  {k:9} {s.n:>4}  {s.escalation_rate:>7.0%}  "
              f"{s.false_clear_rate:>8.0%} {_bar(s.false_clear_rate, 8)}  "
              f"{s.over_ask_rate:>7.0%}  {s.justified_ask_rate:>7.0%}")
    print(f"  -> trustworthy up to drift bin: {instrument.trustworthy_ceiling(bins)} "
          f"(highest bin with zero false-clears)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="also run the LLM agent")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    clean = build_clean_claims()
    stream = poison(clean, seed=args.seed)
    corrupts = Counter(c.corruption for c in stream if c.corruption)
    n_err = sum(1 for c in stream if c.truth == "error")
    n_amb = sum(1 for c in stream if c.truth == "needs_human")
    print(f"Built {len(clean)} clean re-derivable claims from real data.")
    print(f"Labeled stream: {len(stream)} claims = {len(stream)-n_err-n_amb} clean + "
          f"{n_err} hard errors + {n_amb} genuinely-ambiguous (needs-human) {dict(corrupts)}.")
    print("  judge-catchable errors break the arithmetic; unit_swap needs reasoning; "
          "unverifiable needs JUDGMENT (the only right move is to ask a human).")

    agents = [JudgeOnlyAgent(), StationarityAgent(threshold=0.6)]
    if args.llm:
        have_sdk = importlib.util.find_spec("anthropic") is not None
        have_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        if have_sdk and have_key:
            agents.append(LLMAgent())
            print("\n[--llm on] one quick model call per per_million claim that passes the judge "
                  "(~150 calls, ~1-2 min; progress dots on stderr).")
        else:
            why = []
            if not have_sdk:
                why.append("anthropic not importable in THIS interpreter "
                           "-> run: uv run --extra proposer python -m bonds_instrument --llm")
            if not have_key:
                why.append("ANTHROPIC_API_KEY not set in this shell -> run: export ANTHROPIC_API_KEY=...")
            print("\n[--llm skipped] " + "; ".join(why))

    all_findings = {}
    results = {}
    for agent in agents:
        bins = instrument.run(agent, stream)
        results[agent.name] = bins
        all_findings[agent.name] = instrument.run.last_findings
        print_curve(agent.name, bins)

    # artifacts
    out = Path("artifacts/bonds")
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "findings.jsonl", "w", encoding="utf-8") as fh:
        for agent_name, finds in all_findings.items():
            for row in finds:
                fh.write(json.dumps({"agent": agent_name, **row}) + "\n")
    _write_regions(out / "REGIONS.md", results, corrupts, len(clean))

    print("\n=== benchmark summary — rank by judgment (lower dangerous + wasted = better) ===")
    print(f"  {'agent':24} {'dangerous':>9}  {'wasted-ask':>10}  {'good-ask':>8}  {'region':>9}")
    for name, bins in results.items():
        ov = instrument.overall(bins)
        print(f"  {name:24} {ov['false_clear_rate']:>8.0%}  {ov['over_ask_rate']:>9.0%}  "
              f"{ov['justified_ask_rate']:>7.0%}  {instrument.trustworthy_ceiling(bins):>9}")

    print(f"\nWrote {out/'findings.jsonl'} and {out/'REGIONS.md'}")
    print("\nTwo-sided now: 'dangerous' = cleared an error OR an unverifiable claim (acted past its\n"
          "edge); 'wasted-ask' = escalated something it should have resolved. The best agent answers\n"
          "what's answerable AND asks a human on exactly the unverifiable residue — never-escalate\n"
          "agents now visibly false-clear the ambiguous cases. Swap in any two agents/models to rank them.")
    return 0


def _write_regions(path, results, corrupts, n_clean) -> None:
    lines = ["# Bond agents — measured trustworthy regions\n",
             f"_{n_clean} re-derivable claims from real data; manufactured labels {dict(corrupts)} "
             "(catchable + unit_swap = errors; unverifiable = needs-human)._\n",
             "Two-sided benchmark. **dangerous** = cleared an error or an unverifiable claim "
             "(acted past its edge). **wasted-ask** = escalated something it should have resolved. "
             "The region is the highest drift band with zero false-clears.\n"]
    for name, bins in results.items():
        ov = instrument.overall(bins)
        lines.append(f"## {name}\n- **Region: trustworthy up to `{instrument.trustworthy_ceiling(bins)}`** "
                     f"· dangerous={ov['false_clear_rate']:.0%} · wasted-ask={ov['over_ask_rate']:.0%} "
                     f"· good-ask={ov['justified_ask_rate']:.0%}")
        for k in _BINKEYS:
            s = bins[k]
            if s.n == 0:
                continue
            lines.append(f"  - `{k}`: n={s.n}, escalate={s.escalation_rate:.0%}, "
                         f"false-clear={s.false_clear_rate:.0%}, over-ask={s.over_ask_rate:.0%}, "
                         f"just-ask={s.justified_ask_rate:.0%}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
