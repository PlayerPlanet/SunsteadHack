"""Escalation helpers — query pending human judgments."""


def pending_escalations(logclient) -> list[dict]:
    """Retrieve all pending escalations (crossings requiring human judgment).

    Uses logclient.read_crossings() for backend-agnostic access.

    Args:
        logclient: LogClient instance.

    Returns:
        List of crossing dicts with requires_human_judgment=True.
    """
    return logclient.read_crossings(filter={"requires_human_judgment": True})
