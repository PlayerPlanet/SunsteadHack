"""MCP server for the SunsteadHack control plane operator.

LEGITIMACY BOUNDARY: This server exposes the operator surface (task registration,
run dispatch, escalation adjudication) but NEVER exposes scoring, benchmarking, or
silent mutations. Humans remain in the loop for governance decisions via the MCP
adjudicate tool (when a task escalates to requires_human_judgment).

Tools are thin wrappers over operator methods, translating JSON inputs/outputs for MCP.
The tool logic is defined as module-level functions (tool_*) so they can be unit-tested
independently of the mcp runtime. The `build_server()` function wires them to FastMCP.
"""

import dataclasses
import datetime
import json
import os
from typing import Any

from cleanroom.control.registry.types import TaskSpec
from cleanroom.control.server.wiring import (
    make_operator,
    make_logclient,
    make_dispatch_ctx,
    governance_pore,
)


def _json_safe(obj):
    """Recursively coerce datetimes to ISO strings so tool results are plain JSON.

    The real Postgres backend returns timestamptz columns (e.g. crossing.created_at,
    run.started_at) as datetime objects; the in-memory fixture does not. Coerce here
    so the MCP tool surface is backend-agnostic.
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    return obj


# ==================== Tool Logic Functions (Unit-Testable) ====================


def _enforce(tool_name: str) -> None:
    """Enforce per-tool OAuth scope when an authenticated principal is in context.

    The HTTP transport (cleanroom.control.server.http_app) sets current_principal
    after validating the bearer token; here we check that principal holds the scope
    this tool requires. In stdio/local mode no principal is set, so this is a no-op —
    which keeps the local plugin subprocess and the direct unit tests unchanged.
    """
    from cleanroom.control.server.auth import authorize_tool
    from cleanroom.control.server.context import current_principal

    principal = current_principal.get()
    if principal is not None:
        authorize_tool(principal, tool_name)


def tool_list_tasks() -> list[dict]:
    """List all active tasks.

    Returns:
        List of task dicts.
    """
    _enforce("list_tasks")
    operator = make_operator()
    tasks = operator.list_tasks()
    return [dataclasses.asdict(t) for t in tasks]


def tool_get_task(task_id: str) -> dict | None:
    """Get a task by ID.

    Args:
        task_id: Task identifier.

    Returns:
        Task dict or None.
    """
    _enforce("get_task")
    operator = make_operator()
    task = operator.get_task(task_id)
    return dataclasses.asdict(task) if task else None


def tool_register_task(spec_json: str) -> str:
    """Register a new task (governance-gated).

    Args:
        spec_json: Task spec as JSON string.

    Returns:
        task_id (string).

    Raises:
        ValueError: If spec_json is invalid.
    """
    _enforce("register_task")
    try:
        spec_dict = json.loads(spec_json)
        spec = TaskSpec(**spec_dict)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise ValueError(f"Invalid task spec JSON: {e}")

    operator = make_operator()
    logclient = make_logclient()
    task_id = operator.register_task(spec, pore=governance_pore(), logclient=logclient)
    return task_id


def tool_dispatch_run(task_id: str, model: str, iterations: int = 10) -> str:
    """Dispatch a run (fire-and-return).

    Args:
        task_id: Task identifier.
        model: Model name for proposer.
        iterations: Number of iterations (default 10).

    Returns:
        run_id (string).
    """
    _enforce("dispatch_run")
    operator = make_operator()
    logclient = make_logclient()
    ctx = make_dispatch_ctx(logclient)
    # In a remote deployment set CLEANROOM_DISPATCH_MODE=queue so this (stateless,
    # load-balanced) web tier enqueues the run for a worker instead of running it in
    # a request thread. Local stdio defaults to "thread" (single trusted process).
    mode = os.environ.get("CLEANROOM_DISPATCH_MODE", "thread")
    run_id = operator.dispatch_run(
        task_id, model=model, iterations=iterations, ctx=ctx, mode=mode
    )
    return run_id


def tool_get_run(run_id: str) -> dict | None:
    """Get run status by ID.

    Args:
        run_id: Run identifier.

    Returns:
        RunStatus dict or None.
    """
    _enforce("get_run")
    operator = make_operator()
    status = operator.get_run(run_id)
    return _json_safe(dataclasses.asdict(status)) if status else None


def tool_list_runs(filter_json: str | None = None) -> list[dict]:
    """List runs, optionally filtered.

    Args:
        filter_json: Optional filter as JSON string (e.g., '{"state":"running"}').

    Returns:
        List of RunStatus dicts.

    Raises:
        ValueError: If filter_json is invalid.
    """
    _enforce("list_runs")
    operator = make_operator()
    filter_dict = None
    if filter_json:
        try:
            filter_dict = json.loads(filter_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid filter JSON: {e}")
    runs = operator.list_runs(filter=filter_dict)
    return [_json_safe(dataclasses.asdict(r)) for r in runs]


def tool_cancel_run(run_id: str) -> None:
    """Request cancellation of a run.

    Args:
        run_id: Run identifier.
    """
    _enforce("cancel_run")
    operator = make_operator()
    operator.cancel_run(run_id)


def tool_pending_escalations() -> list[dict]:
    """List pending escalations (crossings requiring human judgment).

    Returns:
        List of crossing dicts.
    """
    _enforce("pending_escalations")
    operator = make_operator()
    logclient = make_logclient()
    return _json_safe(operator.pending_escalations(logclient))


def tool_adjudicate(
    crossing_id: int,
    decision: str,
    rationale: str | None = None,
    judge: str = "human",
) -> None:
    """Human decision on a crossing.

    Args:
        crossing_id: Crossing ID.
        decision: Decision (approve/reject/allow/block).
        rationale: Optional explanation.
        judge: Judge identifier (default 'human').
    """
    _enforce("adjudicate")
    operator = make_operator()
    logclient = make_logclient()
    operator.adjudicate(
        crossing_id,
        decision,
        rationale=rationale,
        judge=judge,
        logclient=logclient,
    )


def tool_read_curve(task_id: str) -> list[dict]:
    """Read performance curve for a task.

    Args:
        task_id: Task identifier.

    Returns:
        List of experiment dicts.
    """
    _enforce("read_curve")
    operator = make_operator()
    logclient = make_logclient()
    return _json_safe(operator.read_curve(task_id, logclient=logclient))


def tool_read_boundary() -> dict:
    """Read the boundary instrument: spatial + longitudinal readings.

    Returns:
        {"spatial": [...], "longitudinal": [...], "proxy_caveat": str}.
    """
    _enforce("read_boundary")
    operator = make_operator()
    logclient = make_logclient()
    return _json_safe(operator.read_boundary(logclient=logclient))


# ==================== MCP Server Setup ====================


def build_server() -> "Any":
    """Build and return the MCP FastMCP server with registered tools.

    Lazy-imports mcp so the module can be imported without mcp present.

    Returns:
        The FastMCP server instance.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        raise ImportError(
            "mcp library not found. Install it with: pip install 'cleanroom[control]' (or pip install mcp)"
        )

    server = FastMCP(
        name="sunstead-control",
        instructions="Operate the SunsteadHack autoresearch control plane",
    )

    # Register tools (FastMCP API: add_tool(fn, name=..., description=...)).
    # Explicit names keep the operator surface clean (no tool_ prefix) and match
    # the frozen tool surface in issue #5 and the plugin slash commands.
    server.add_tool(tool_list_tasks, name="list_tasks", description="List all active tasks")
    server.add_tool(tool_get_task, name="get_task", description="Get a task by ID")
    server.add_tool(
        tool_register_task,
        name="register_task",
        description="Register a new task (governance-gated; may escalate for human judgment)",
    )
    server.add_tool(
        tool_dispatch_run,
        name="dispatch_run",
        description="Dispatch a run (fire-and-return); returns run_id",
    )
    server.add_tool(tool_get_run, name="get_run", description="Get run status (pollable)")
    server.add_tool(tool_list_runs, name="list_runs", description="List runs, optionally filtered")
    server.add_tool(tool_cancel_run, name="cancel_run", description="Request cancellation of a run")
    server.add_tool(
        tool_pending_escalations,
        name="pending_escalations",
        description="List escalations requiring human judgment",
    )
    server.add_tool(
        tool_adjudicate, name="adjudicate", description="Write a human judgment on a crossing"
    )
    server.add_tool(tool_read_curve, name="read_curve", description="Read performance curve for a task")
    server.add_tool(
        tool_read_boundary,
        name="read_boundary",
        description="Read the boundary instrument (escalation-rate-vs-drift + escalations-per-unit-work)",
    )

    return server


def main():
    """Entry point: run the stdio MCP server."""
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
