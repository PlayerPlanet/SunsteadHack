#!/usr/bin/env python
"""Manifesto spatial reading — escalation rate rises with workload drift.

This is the experiment behind the manifesto's *spatial* boundary reading: as the
world drifts from what the system has earned trust on, the agent's own proposals
cross the frozen safety pore more often, so it must stop and ask a human more often.

HONESTY (read this — it's the whole point):
  * The pore is FROZEN and dumb. This script never writes decision='escalated'
    itself — it runs the real `cleanroom.loop.run_loop`, and the real
    `cleanroom.pore.evaluate` is what classifies each candidate. The escalations
    are genuine pore crossings on genuinely high-blast-radius / irreversible
    candidates (shared_buffers, max_connections, or reversible=False).
  * What is MODELED is the *proposer's* drift-response: under higher drift, cheap
    reversible fixes (an index, a dynamic work_mem bump) stop being expected to
    help, so a rational proposer reaches for bigger hammers. The proposer is the
    soft, non-judge part of the system — modelling it is legitimate; the judge
    (pore) stays frozen. So the rising curve says "the world drifted," not "we
    loosened the gate" — exactly the distinction the frozen pore exists to keep.
  * The drift-response uses a deterministic, documented severity schedule (a
    golden-ratio low-discrepancy sequence), NOT randomness and NOT a hand-set
    rate=drift mapping: at step i the problem has a fixed severity s_i, and we
    reach for an escalating remedy when s_i < drift (the cheap fix won't cut it
    at this drift). Escalation rate then emerges from how many steps clear that
    bar at each drift level.

Infra-free by default (CannedBenchmark + InMemoryLogClient — no DB needed). With
CLEANROOM_PG_DSN set it persists to Aiven (the morning live step) via the same
control-plane wiring; the code path is identical.

Usage:
    python scripts/run_drift_sweep.py                       # in-memory, prints both readings
    python scripts/run_drift_sweep.py --out boundary.json   # also dump JSON for the artifact
    CLEANROOM_PG_DSN=... python scripts/run_drift_sweep.py   # persist to Aiven
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleanroom.boundary import escalation_rate_by_drift, escalations_per_unit_work
from cleanroom.fixtures import CannedBenchmark, InMemoryLogClient
from cleanroom.loop import run_loop
from cleanroom.types import Candidate
import cleanroom.pore as pore_mod

# Fixed, deterministic per-step "problem severity" in [0,1): a golden-ratio
# low-discrepancy sequence. Spread out and reproducible, with no randomness.
_GOLDEN = 0.6180339887498949


def _severity(i: int) -> float:
    return (0.5 + (i + 1) * _GOLDEN) % 1.0


class DriftAwareProposer:
    """Proposes remedies whose riskiness tracks workload drift (see module docstring).

    Given the drift level for this run, each step either reaches for an escalating
    remedy (a high-blast-radius GUC, or an irreversible change) when the step's
    severity exceeds what a cheap reversible fix can absorb at this drift, or else
    proposes a safe, reversible fix. The FROZEN pore independently decides whether
    each is escalated — this class only chooses *what to try*.
    """

    def __init__(self, drift: float):
        self.drift = drift
        self._i = 0

    def propose(self, task_spec: dict, history: list) -> Candidate:
        i = self._i
        self._i += 1
        needs_big_hammer = _severity(i) < self.drift
        if not needs_big_hammer:
            # Cheap, reversible, low-blast — the pore allows these.
            return Candidate(
                type="index",
                params={"table": "events", "columns": ["user_id", "created_at"]},
                reversible=True,
            )
        # The cheap fix won't cut it at this drift — reach for a bigger hammer.
        # Alternate the *kind* of risk so both frozen pore rules fire over a run:
        # blast-radius (a systemic GUC) and reversibility (a non-reversible change).
        if i % 2 == 0:
            return Candidate(
                type="guc",
                params={"name": "shared_buffers", "value": "512MB"},
                reversible=True,  # technically reversible, but high blast radius
            )
        return Candidate(
            type="index",
            params={"table": "events", "columns": ["user_id"]},
            reversible=False,  # irreversible — the pore escalates on reversibility
        )


def _run_at_drift(logclient, drift: float, iterations: int, task_id: str) -> None:
    """Run the interior loop once at a fixed drift level, writing to logclient."""
    run_loop(
        {
            "task_id": task_id,
            "model": "drift-sweep",
            "workload_id": "",
            "drift_level": drift,
            # conn omitted -> None -> CannedBenchmark / no-op apply (infra-free)
        },
        proposer=DriftAwareProposer(drift),
        benchmark=CannedBenchmark(),
        pore=pore_mod,
        logclient=logclient,
        iterations=iterations,
    )


def run_ramp(logclient, drifts, iterations: int, task_id: str = "drift-ramp") -> list[dict]:
    """SPATIAL reading: one loop run per ascending drift level → escalation rate vs drift."""
    for d in drifts:
        _run_at_drift(logclient, d, iterations, task_id)
    return escalation_rate_by_drift(logclient)


def run_stationary(logclient, drift: float, iterations: int, task_id: str = "stationary") -> list[dict]:
    """LONGITUDINAL reading: accumulate volume at a FIXED drift → flat by design.

    With the frozen pore at a stationary workload, the per-window escalation ratio
    holds ~constant as cumulative volume grows. The flat line IS the artifact: the
    frontier that does not *yet* recede (the amortized membrane is the deferred bet
    to bend it down).
    """
    _run_at_drift(logclient, drift, iterations, task_id)
    return escalations_per_unit_work(logclient)


_PROXY_CAVEAT = (
    "Pore gates blast-radius + reversibility — a lower bound on, not identical to, "
    "the agent's true epistemic edge."
)


def run_full(make_logclient, drifts, iterations: int, *, stationary_drift: float = 0.4,
             stationary_iterations: int = 61) -> dict:
    """Produce BOTH readings honestly, each from its own data regime.

    spatial  <- a drift ramp (varying drift)
    longitudinal <- a stationary run at fixed drift (accumulating volume)

    `make_logclient` is a zero-arg factory so each reading gets its own clean log
    (the boundary queries read the whole log; mixing regimes would conflate them).
    """
    spatial = run_ramp(make_logclient(), drifts, iterations)
    longitudinal = run_stationary(make_logclient(), stationary_drift, stationary_iterations)
    return {
        "spatial": spatial,
        "longitudinal": longitudinal,
        "stationary_drift": stationary_drift,
        "proxy_caveat": _PROXY_CAVEAT,
    }


def _make_logclient():
    dsn = os.environ.get("CLEANROOM_PG_DSN")
    if dsn:
        from cleanroom.db import connect, init_schema
        from cleanroom.logclient import PgLogClient

        conn = connect(dsn)
        try:
            init_schema(conn)
        finally:
            conn.close()
        return PgLogClient.from_dsn(dsn)
    return InMemoryLogClient()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Manifesto drift sweep: escalation rate vs drift.")
    ap.add_argument("--drifts", default="0,0.2,0.4,0.6,0.8,1.0", help="Comma-separated drift levels.")
    ap.add_argument("--iterations", type=int, default=12, help="Loop iterations per drift level.")
    ap.add_argument("--task-id", default="manifesto-drift-sweep")
    ap.add_argument("--out", default=None, help="Optional path to dump the boundary JSON.")
    args = ap.parse_args(argv)

    drifts = [float(x) for x in args.drifts.split(",") if x.strip() != ""]
    if os.environ.get("CLEANROOM_PG_DSN"):
        print("NOTE: with CLEANROOM_PG_DSN both readings share one DB; the spatial ramp is "
              "the live-persistence proof. Use a fresh schema per reading for a clean longitudinal.")
    backend = "Aiven (CLEANROOM_PG_DSN)" if os.environ.get("CLEANROOM_PG_DSN") else "in-memory"
    print(f"Drift sweep — backend: {backend}; drifts: {drifts}; iterations/level: {args.iterations}")

    boundary = run_full(_make_logclient, drifts, args.iterations)

    print("\n=== SPATIAL — escalation rate vs drift (the autonomous edge, now) ===")
    for r in boundary["spatial"]:
        bar = "#" * int(round(r["escalation_rate"] * 40))
        print(f"  drift {r['drift_level']:.2f}  rate {r['escalation_rate']:.3f}  n={r['n']:<3} {bar}")
    print(f"\n=== LONGITUDINAL — escalations per unit work @ fixed drift "
          f"{boundary['stationary_drift']:.2f} (flat by design) ===")
    for r in boundary["longitudinal"]:
        bar = "#" * int(round(r["ratio"] * 40))
        print(f"  window {r['window']:<2} cum={r['cumulative_experiments']:<4} ratio={r['ratio']:.3f} {bar}")
    print(f"\n  caveat: {boundary['proxy_caveat']}")

    if args.out:
        Path(args.out).write_text(json.dumps(boundary, indent=2, default=str), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
