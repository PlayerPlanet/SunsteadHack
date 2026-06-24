"""Seed synthetic experiment log for Phase-0 testing.

Story C (GitHub issue #4) owns this implementation.

Fills experiment/crossing/judgment records across drift_level 0→high AND a
cumulative-volume timeline so both curves and the dashboard can be built and
validated before A's real log exists.

Design:
  - drift_levels [0.0, 0.25, 0.5, 0.75, 1.0] with escalation_prob = 0.05 + drift*0.60
  - Experiments are interleaved (round-robin across drift levels) so IDs form a
    longitudinal timeline; with the frozen pore the longitudinal curve is flat.
  - Two models ('haiku' cheap, 'sonnet' expensive) alternate to populate the model axis.
  - Escalated experiments get a crossing + judgment record.
"""

import random

DRIFT_LEVELS = [0.0, 0.25, 0.5, 0.75, 1.0]
MODELS = ["haiku", "sonnet"]
COST_BY_MODEL = {"haiku": 0.5, "sonnet": 2.0}


def _esc_prob(drift: float) -> float:
    return 0.05 + drift * 0.60


def seed(logclient, *, n_per_drift: int = 20, seed_val: int = 42) -> None:
    """Populate logclient with synthetic data spanning drift levels and cumulative volume.

    Args:
        logclient: Any LogClient (InMemoryLogClient or psycopg-backed).
        n_per_drift: Experiments generated per drift level.
        seed_val: Random seed for reproducibility.
    """
    rng = random.Random(seed_val)

    for round_i in range(n_per_drift):
        for drift in DRIFT_LEVELS:
            model = MODELS[round_i % len(MODELS)]
            escalated = rng.random() < _esc_prob(drift)
            decision = "escalated" if escalated else rng.choice(["keep", "discard"])
            baseline_p99 = 100.0
            candidate_p99 = max(1.0, baseline_p99 * (0.80 + rng.random() * 0.40) + rng.gauss(0, 3.0))

            exp_id = logclient.write_experiment(
                task_id=f"synthetic-drift-{drift:.2f}",
                model=model,
                drift_level=drift,
                candidate={
                    "type": "index",
                    "params": {"round": round_i, "drift": drift},
                    "reversible": True,
                },
                baseline_p99=baseline_p99,
                candidate_p99=candidate_p99,
                cost_estimate=COST_BY_MODEL[model],
                correctness_ok=not escalated,
                within_noise=not escalated,
                decision=decision,
            )

            if escalated:
                crossing_id = logclient.write_crossing(
                    experiment_id=exp_id,
                    pore="blast_radius",
                    risk_level="high" if drift >= 0.5 else "medium",
                    requires_human_judgment=True,
                    action={"action": "escalate", "reason": f"drift={drift:.2f}"},
                )
                logclient.write_judgment(
                    crossing_id=crossing_id,
                    judge="synthetic-rule",
                    judge_kind="rule",
                    decision="escalate",
                    rationale=f"Synthetic escalation at drift={drift:.2f}, round={round_i}",
                )


def main():
    """Seed an in-memory log, run all three Story-C analyses, print results."""
    from cleanroom.fixtures import InMemoryLogClient
    from cleanroom.boundary import escalation_rate_by_drift, escalations_per_unit_work
    from cleanroom.dashboard import render

    logclient = InMemoryLogClient()
    seed(logclient, n_per_drift=30)

    total = len(logclient.read_experiments())
    print(f"Seeded {total} experiments\n")

    print("=== (A) Spatial curve: escalation rate vs drift ===")
    print("NOTE: proxy / lower-bound of legitimacy boundary — not the true edge")
    for row in escalation_rate_by_drift(logclient):
        bar = "█" * int(row["escalation_rate"] * 30)
        print(f"  drift={row['drift_level']:.2f}  {row['escalation_rate']:5.1%}  n={row['n']:>3}  {bar}")

    print("\n=== (B) Longitudinal curve: escalations per unit work ===")
    print("NOTE: flat by design with frozen pore — the frontier does not yet recede")
    for row in escalations_per_unit_work(logclient):
        print(f"  vol={row['cumulative_experiments']:>4}  {row['ratio']:5.1%}  ({row['escalated']}/{row['total']})")

    print("\n=== Full dashboard ===")
    print(render(logclient, task_id=None))


if __name__ == "__main__":
    main()
