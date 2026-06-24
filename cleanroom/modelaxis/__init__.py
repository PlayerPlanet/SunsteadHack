"""Model and resource axis analysis.

Story C (GitHub issue #4) owns dimensionality and cost analysis across
multiple models and resource configurations.
"""

from collections import defaultdict


def region_per_dollar(logclient) -> list[dict]:
    """Compute the legitimate-autonomy region per dollar for each model.

    The 'autonomy region' is experiments where the agent acted autonomously
    (decision in {'keep', 'discard'}) without escalating to a human. Dividing
    by total cost gives a measure of how much autonomous work each dollar buys.

    Two cells proves the axis is measurable; the full model matrix is the
    post-hackathon paper.

    Args:
        logclient: LogClient for reading experiment records.

    Returns:
        List of {model, autonomous, escalated, total, total_cost,
        region_per_dollar} records, sorted by region_per_dollar descending.
    """
    experiments = logclient.read_experiments()
    buckets: dict = defaultdict(lambda: {"autonomous": 0, "escalated": 0, "total_cost": 0.0})

    for exp in experiments:
        model = exp["model"]
        buckets[model]["total_cost"] += exp.get("cost_estimate") or 0.0
        if exp["decision"] == "escalated":
            buckets[model]["escalated"] += 1
        else:
            buckets[model]["autonomous"] += 1

    result = []
    for model, stats in buckets.items():
        cost = stats["total_cost"] or 1.0
        autonomous = stats["autonomous"]
        escalated = stats["escalated"]
        result.append({
            "model": model,
            "autonomous": autonomous,
            "escalated": escalated,
            "total": autonomous + escalated,
            "total_cost": stats["total_cost"],
            "region_per_dollar": autonomous / cost,
        })

    return sorted(result, key=lambda r: r["region_per_dollar"], reverse=True)
