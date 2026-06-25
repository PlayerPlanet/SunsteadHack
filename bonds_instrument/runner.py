"""Input-driven benchmark entrypoint — Cut A of the 'bring your own agent' surface.

Two things VARY as inputs: the **materials** (the bond CSVs) and the **candidate
agent**. The ruler stays frozen. Per issue #28 the benchmark is generated the
*non-agentic* way — re-derive the decidable layer (`judge.py`) to find the clean
pool, then PLANT labeled errors / strip provenance (`claims.poison`). The candidate
never sees a label; we hold the answer key because we manufactured it. No agent ever
decides where the ambiguity is or whether the candidate was right.

    run_benchmark(materials_path, agent_import) -> scorecard dict

`agent_import` is "module.path:Attr" resolving to an instrument agent — anything
exposing `review(view) -> Decision` and a `name`. That is the whole BYO-agent
contract; the reference adapter for the Arctal take-home agent is
`bonds_instrument.candidates:DQAgentCandidate`.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import time
from collections import Counter
from pathlib import Path

from . import instrument, judge
from .claims import CATCHABLE, build_clean_claims, poison

log = logging.getLogger("bonds_instrument.benchmark")


def _ensure_logging(verbose: bool) -> None:
    """Attach a stderr handler once. INFO by default, DEBUG when verbose."""
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[bench] %(message)s"))
        log.addHandler(h)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)


def generation_stats(clean, stream) -> dict:
    """Self-check the generator's load-bearing invariants (issue #28).

    Returns the three equalities that make the benchmark non-circular:
      * every clean-pool claim passes the frozen judge,
      * every judge-CATCHABLE plant actually breaks the judge,
      * every unit_swap (uncatchable) still passes the judge — so only reasoning,
        not arithmetic, can catch it.
    If any of these don't hold, the ruler is miscalibrated and the run is untrustworthy.
    """
    clean_pass = sum(1 for c in clean if judge.passes(c.view))
    catch_broke = catch_total = uncatch_evade = uncatch_total = 0
    for c in stream:
        if c.corruption in CATCHABLE:
            catch_total += 1
            catch_broke += 0 if judge.passes(c.view) else 1
        elif c.corruption == "unit_swap":
            uncatch_total += 1
            uncatch_evade += 1 if judge.passes(c.view) else 0
    return {
        "clean_pool": len(clean), "clean_pass_judge": clean_pass,
        "catchable_break_judge": [catch_broke, catch_total],
        "uncatchable_evade_judge": [uncatch_evade, uncatch_total],
    }


def load_agent(agent_import: str, *, use_llm: bool = False):
    """Resolve "module.path:attr" to an instrument agent (has .review + .name).

    `attr` may be a class/factory (called to build the agent) or a ready instance.
    A callable is tried with `use_llm=` first (so two-mode agents pick up the flag),
    then with no args. Kept deliberately small — the contract is just `.review(view)`.
    """
    if ":" not in agent_import:
        raise ValueError(f"agent_import must be 'module.path:attr', got {agent_import!r}")
    mod_name, attr = agent_import.split(":", 1)
    obj = getattr(importlib.import_module(mod_name), attr)
    if isinstance(obj, type) or callable(obj):
        try:
            agent = obj(use_llm=use_llm)
        except TypeError:
            agent = obj()
    else:
        agent = obj
    if not hasattr(agent, "review"):
        raise TypeError(f"{agent_import} -> {type(agent).__name__} has no .review(view) method")
    if not getattr(agent, "name", None):
        agent.name = attr
    return agent


def run_benchmark(materials_path: str | None, agent_import: str, *,
                  use_llm: bool = False, seed: int = 7,
                  out_dir: str = "artifacts/bonds", verbose: bool = False) -> dict:
    """Benchmark one candidate against the materials; return a JSON-safe scorecard."""
    _ensure_logging(verbose)
    if materials_path:  # materials as input: point the frozen loaders at this data
        os.environ["BONDS_DATA_DIR"] = str(Path(materials_path).expanduser().resolve())
    log.info("materials: %s", os.environ.get("BONDS_DATA_DIR", "<bundled sample>"))

    # --- Generate the benchmark the #28 way (no agent in this path) ----------- #
    t = time.time()
    clean = build_clean_claims()       # re-derive -> the claims the frozen judge passes
    stream = poison(clean, seed=seed)  # plant known errors + strip provenance -> the key
    corrupts = Counter(c.corruption for c in stream if c.corruption)
    gen = generation_stats(clean, stream)
    log.info("generated %d claims from %d clean in %.2fs | planted=%s",
             len(stream), len(clean), time.time() - t, dict(corrupts))
    log.info("judge self-check: clean_pass=%d/%d  catchable_break=%d/%d  unit_swap_evades=%d/%d",
             gen["clean_pass_judge"], gen["clean_pool"],
             *gen["catchable_break_judge"], *gen["uncatchable_evade_judge"])
    if (gen["clean_pass_judge"] != gen["clean_pool"]
            or gen["catchable_break_judge"][0] != gen["catchable_break_judge"][1]
            or gen["uncatchable_evade_judge"][0] != gen["uncatchable_evade_judge"][1]):
        log.warning("RULER MISCALIBRATED — a judge invariant failed; scores are untrustworthy.")

    # --- Score the candidate (it never sees a label) -------------------------- #
    t = time.time()
    agent = load_agent(agent_import, use_llm=use_llm)
    log.info("agent: %s (%s)%s", agent.name, agent_import, "  [llm]" if use_llm else "")
    bins = instrument.run(agent, stream)
    ov = instrument.overall(bins)
    log.info("scored in %.2fs | region=%s dangerous=%.0f%% wasted-ask=%.0f%% good-ask=%.0f%%",
             time.time() - t, instrument.trustworthy_ceiling(bins),
             ov["false_clear_rate"] * 100, ov["over_ask_rate"] * 100, ov["justified_ask_rate"] * 100)
    scorecard = {
        "agent": agent.name,
        "agent_import": agent_import,
        "materials": os.environ.get("BONDS_DATA_DIR", "<bundled sample>"),
        "n_claims": len(stream),
        "stream_composition": dict(corrupts),
        "generation": gen,  # the #28 ruler self-check (clean pass / catchable break / unit_swap evades)
        "region": instrument.trustworthy_ceiling(bins),
        "overall": {
            "false_clear_rate": round(ov["false_clear_rate"], 4),  # dangerous: acted past edge
            "over_ask_rate": round(ov["over_ask_rate"], 4),        # wasted-ask
            "justified_ask_rate": round(ov["justified_ask_rate"], 4),  # good-ask
        },
        "by_drift_bin": [
            {"bin": b.bin, "n": b.n,
             "escalation_rate": round(b.escalation_rate, 4),
             "false_clear_rate": round(b.false_clear_rate, 4),
             "over_ask_rate": round(b.over_ask_rate, 4),
             "justified_ask_rate": round(b.justified_ask_rate, 4)}
            for b in bins.values() if b.n
        ],
        "doctrine": "judge is frozen + non-agentic (re-derivation + planted labels, issue #28); "
                    "the interpretive layer is human territory and is NOT scored.",
    }

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scorecard.json").write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    log.info("wrote %s", out / "scorecard.json")
    return scorecard


def main(argv=None) -> int:
    """Direct CLI for the input-driven benchmark (the MCP tool wraps this same path).

        python -m bonds_instrument.runner --agent module:Attr [--materials DIR] [--llm] [-v]
    """
    import argparse

    ap = argparse.ArgumentParser(prog="bonds_instrument.runner",
                                 description="Benchmark a candidate agent against bond materials.")
    ap.add_argument("--agent", required=True, metavar="module:Attr",
                    help="candidate exposing review(view)->Decision, e.g. "
                         "bonds_instrument.candidates:DQAgentCandidate")
    ap.add_argument("--materials", metavar="DIR", help="dir of bond CSVs (default: bundled sample)")
    ap.add_argument("--llm", action="store_true", help="enable the candidate's LLM tier")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("-v", "--verbose", action="store_true", help="DEBUG-level logs")
    args = ap.parse_args(argv)

    sc = run_benchmark(args.materials, args.agent, use_llm=args.llm, seed=args.seed,
                       verbose=args.verbose)
    print(json.dumps(sc, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
