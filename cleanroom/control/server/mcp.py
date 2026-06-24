"""Thin MCP adapter for the Operator.

PHASE-0 STUB: This module defines the tool surface for integration with an MCP server.
No MCP server library is currently wired. This is a documented placeholder.

When an MCP server is available, implement these tools:
  - list_tasks() -> list[TaskSpec]
  - get_task(task_id: str) -> TaskSpec | None
  - register_task(spec_json: str, *, pore, logclient) -> str
  - dispatch_run(task_id: str, model: str, iterations: int) -> str
  - get_run(run_id: str) -> RunStatus | None
  - list_runs(filter_json: str | None) -> list[RunStatus]
  - cancel_run(run_id: str) -> None
  - pending_escalations(*, logclient) -> list[dict]
  - adjudicate(crossing_id: int, decision: str, *, logclient) -> None
  - read_curve(task_id: str, *, logclient) -> list[dict]

All methods delegate to Operator instance.
"""

__doc__ = """
MCP Tool Definitions for Control Plane

Tool: list_tasks
  Description: List all active task specifications
  Input: (none)
  Output: list of TaskSpec objects (as JSON)

Tool: get_task
  Description: Retrieve a task by ID
  Input: task_id (string)
  Output: TaskSpec object (as JSON) or null

Tool: register_task
  Description: Register a new task (governance-gated)
  Input: spec_json (string), injected pore/logclient
  Output: task_id (string)

Tool: dispatch_run
  Description: Dispatch a run (fire-and-return, background thread)
  Input: task_id (string), model (string), iterations (int, default 10)
  Output: run_id (string)

Tool: get_run
  Description: Get run status (pollable)
  Input: run_id (string)
  Output: RunStatus object (as JSON) or null

Tool: list_runs
  Description: List runs, optionally filtered
  Input: filter_json (optional string, e.g. '{"state":"running"}')
  Output: list of RunStatus objects (as JSON)

Tool: cancel_run
  Description: Request cancellation of a run
  Input: run_id (string)
  Output: (none)

Tool: pending_escalations
  Description: List crossings requiring human judgment
  Input: (none)
  Output: list of crossing dicts (as JSON)

Tool: adjudicate
  Description: Human decision on a crossing
  Input: crossing_id (int), decision (string), rationale (optional string)
  Output: (none)

Tool: read_curve
  Description: Read performance curve for a task
  Input: task_id (string)
  Output: list of experiment dicts (as JSON)
"""


# Phase-0 Stub: Uncomment and implement when MCP server library is available.
#
# from cleanroom.control.ops import Operator, OperatorContext
#
# class ControlPlaneTools:
#     """MCP tool implementations wrapping the Operator."""
#
#     def __init__(self, operator: Operator):
#         self.operator = operator
#
#     def list_tasks(self):
#         """List all active tasks."""
#         tasks = self.operator.list_tasks()
#         return [task.__dict__ for task in tasks]
#
#     def get_task(self, task_id: str):
#         """Get task by ID."""
#         task = self.operator.get_task(task_id)
#         return task.__dict__ if task else None
#
#     # ... etc. for each operator method
