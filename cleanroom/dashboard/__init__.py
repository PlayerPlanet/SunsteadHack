"""Dashboard and reporting.

Story C (GitHub issue #4) owns dashboard rendering, visualization, and
real-time reporting of loop and boundary metrics.
"""

from cleanroom.boundary import escalation_rate_by_drift, escalations_per_unit_work
from cleanroom.modelaxis import region_per_dollar


def _bar(value: float, width: int = 28) -> str:
    filled = max(0, min(width, int(round(value * width))))
    return "█" * filled + "░" * (width - filled)


def render(logclient, task_id: str | None) -> str:
    """Render a text dashboard: spatial curve, longitudinal curve, model axis.

    Labelling contract (load-bearing): the spatial curve is a PROXY /
    LOWER-BOUND of the legitimacy boundary, NOT the boundary itself. The
    frozen pore gates blast-radius tripwires (reversibility + estimated risk),
    which correlates with but is NOT "what the agent can stand behind." The
    true edge detector is the deferred calibrated membrane. Labels say so.

    Args:
        logclient: LogClient for reading experiment records.
        task_id: If given, show per-task experiment count; pass None for global.

    Returns:
        Multi-line text dashboard.
    """
    lines: list[str] = []
    W = 70

    def rule(ch="─"):
        return ch * W

    lines += [
        "╔" + "═" * (W - 2) + "╗",
        "║  CLEANROOM BOUNDARY DASHBOARD  (Story C — GitHub issue #4)" + " " * (W - 62) + "║",
        "╚" + "═" * (W - 2) + "╝",
        "",
    ]

    all_exps = logclient.read_experiments()
    if task_id:
        task_exps = logclient.read_experiments({"task_id": task_id})
        lines.append(f"  Task: {task_id}  ({len(task_exps)} experiments)")
    else:
        lines.append(f"  All tasks — {len(all_exps)} experiments total")
    lines.append("")

    # ── Spatial curve ──────────────────────────────────────────────────────
    lines += [
        "  ┌── (A) SPATIAL CURVE: escalation rate vs workload drift " + "─" * 11 + "┐",
        "  │  PROXY / LOWER-BOUND of the legitimacy boundary.                   │",
        "  │  Pore gates blast-radius risk (reversibility + level), not the     │",
        "  │  agent's epistemic edge. Do not mistake the proxy for the real     │",
        "  │  boundary — label it explicitly in every presentation.             │",
        "  └" + "─" * (W - 4) + "┘",
    ]
    spatial = escalation_rate_by_drift(logclient)
    if spatial:
        for row in spatial:
            bar = _bar(row["escalation_rate"])
            lines.append(
                f"  drift={row['drift_level']:.2f}  {bar}  {row['escalation_rate']:5.1%}  n={row['n']}"
            )
    else:
        lines.append("  [no data]")
    lines.append("")

    # ── Longitudinal curve ─────────────────────────────────────────────────
    lines += [
        "  ┌── (B) LONGITUDINAL CURVE: escalations per unit work vs cumulative volume ─┐",
        "  │  Flat by design with the frozen pore — the frontier does not yet recede.  │",
        "  │  This flat line IS the demo beat: the amortized membrane is the bet to    │",
        "  │  bend it down; this instrument is already pointed at it.                  │",
        "  └" + "─" * (W - 4) + "┘",
    ]
    longitudinal = escalations_per_unit_work(logclient)
    if longitudinal:
        max_ratio = max(r["ratio"] for r in longitudinal) or 1.0
        for row in longitudinal:
            bar = _bar(row["ratio"] / max_ratio, width=20)
            lines.append(
                f"  vol={row['cumulative_experiments']:>4}  {bar}  {row['ratio']:5.1%}"
            )
    else:
        lines.append("  [no data]")
    lines.append("")

    # ── Model axis ─────────────────────────────────────────────────────────
    lines += [
        "  ┌── (C) MODEL AXIS: legitimate-autonomy region per dollar " + "─" * 11 + "┐",
        "  │  Two cells proves the axis is measurable.                            │",
        "  │  Full model matrix is the post-hackathon paper.                      │",
        "  └" + "─" * (W - 4) + "┘",
    ]
    axis = region_per_dollar(logclient)
    if axis:
        max_rpd = max(r["region_per_dollar"] for r in axis) or 1.0
        for row in axis:
            bar = _bar(row["region_per_dollar"] / max_rpd, width=20)
            lines.append(
                f"  {row['model']:<10}  auto={row['autonomous']:>4}  esc={row['escalated']:>3}"
                f"  cost=${row['total_cost']:>7.2f}  rgn/$={row['region_per_dollar']:.3f}  {bar}"
            )
    else:
        lines.append("  [no data]")
    lines.append("")

    return "\n".join(lines)
