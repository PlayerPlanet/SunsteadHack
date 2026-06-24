"""Boundary layer — decision gates and escalation analysis.

Story C (GitHub issue #4) owns the boundary benchmark, escalation rate
calculation, and empirical gate tuning.
"""

from collections import defaultdict


def escalation_rate_by_drift(logclient) -> list[dict]:
    """Calculate escalation rate as a function of drift_level.

    Groups all experiments by drift_level and computes the fraction with
    decision='escalated'. This is the spatial curve: where the edge is right now.

    NOTE: This is a proxy / lower-bound of the legitimacy boundary, not the
    boundary itself. The frozen pore gates blast-radius tripwires (reversibility
    + estimated risk level), which correlates with but is NOT identical to
    "what the agent can stand behind" (its epistemic edge). Never mistake the
    proxy for the true boundary — say so in labels and in the pitch.

    Args:
        logclient: LogClient for reading experiment records.

    Returns:
        List of {drift_level, escalation_rate, n} records, sorted by drift_level.
    """
    experiments = logclient.read_experiments()
    buckets: dict[float, list[bool]] = defaultdict(list)
    for exp in experiments:
        buckets[exp["drift_level"]].append(exp["decision"] == "escalated")

    return [
        {
            "drift_level": drift,
            "escalation_rate": sum(flags) / len(flags),
            "n": len(flags),
        }
        for drift in sorted(buckets)
        for flags in [buckets[drift]]
    ]


def escalations_per_unit_work(logclient, *, window_size: int = 10) -> list[dict]:
    """Calculate escalations per unit work over cumulative experiment volume.

    Sorts all experiments by ID (proxy for creation order) and buckets them
    into windows of window_size. For each window computes the escalation ratio
    and the cumulative experiment count at that window's end.

    With the frozen pore this curve is flat by design — the pore fires at a
    constant rate set by rule, not by accumulated history. A flat line here IS
    the demo beat: "the frontier does not yet recede; the amortized membrane is
    the bet to bend it down, and the instrument is already pointed at it."

    Args:
        logclient: LogClient for reading experiment records.
        window_size: Number of experiments per bucketed window.

    Returns:
        List of {window, cumulative_experiments, escalated, total, ratio} records.
    """
    experiments = sorted(logclient.read_experiments(), key=lambda e: e["id"])
    result = []
    for i in range(0, len(experiments), window_size):
        chunk = experiments[i : i + window_size]
        if not chunk:
            continue
        escalated = sum(1 for e in chunk if e["decision"] == "escalated")
        total = len(chunk)
        result.append({
            "window": i // window_size + 1,
            "cumulative_experiments": i + total,
            "escalated": escalated,
            "total": total,
            "ratio": escalated / total,
        })
    return result
