"""Boundary layer — decision gates and escalation analysis.

Story C (GitHub issue #4) owns the boundary benchmark, escalation rate
calculation, and empirical gate tuning.
"""


def escalation_rate_by_drift(logclient) -> list[dict]:
    """Calculate escalation rate as a function of drift_level.

    Args:
        logclient: LogClient for reading experiment records.

    Returns:
        List of {drift_level, escalation_rate, confidence} records.

    Raises:
        NotImplementedError: Story C owns this implementation.
    """
    raise NotImplementedError("escalation_rate_by_drift — owned by Story C, GitHub issue #4")


def escalations_per_unit_work(logclient) -> list[dict]:
    """Calculate escalations per unit work (e.g., per iteration or per second).

    Args:
        logclient: LogClient for reading experiment records.

    Returns:
        List of {time_window, escalations, iterations, ratio} records.

    Raises:
        NotImplementedError: Story C owns this implementation.
    """
    raise NotImplementedError("escalations_per_unit_work — owned by Story C, GitHub issue #4")
