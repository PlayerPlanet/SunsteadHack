"""Dashboard and reporting.

Story C (GitHub issue #4) owns dashboard rendering, visualization, and
real-time reporting of loop and boundary metrics.
"""


def render(logclient, task_id: str) -> str:
    """Render a summary dashboard for a task.

    Args:
        logclient: LogClient for reading experiment records.
        task_id: The task to visualize.

    Returns:
        HTML or text representation of the dashboard.

    Raises:
        NotImplementedError: Story C owns this implementation.
    """
    raise NotImplementedError("render — owned by Story C, GitHub issue #4")
