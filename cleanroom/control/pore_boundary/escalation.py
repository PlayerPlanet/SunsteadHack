"""Escalation helpers — query pending human judgments."""


def pending_escalations(logclient) -> list[dict]:
    """Retrieve all pending escalations (crossings requiring human judgment).

    Phase 0: Reads directly from logclient.crossings (in-memory fixture).
    TODO(integration#4): Replace with logclient.read_crossings(filter={'requires_human_judgment': True})

    Args:
        logclient: LogClient instance (must have .crossings attribute for Phase 0).

    Returns:
        List of crossing dicts with requires_human_judgment=True.
    """
    escalations = []
    for crossing in logclient.crossings:
        if crossing.get("requires_human_judgment"):
            escalations.append(crossing)
    return escalations
