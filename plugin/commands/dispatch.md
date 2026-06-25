---
description: Dispatch an optimization run for an active task (fire-and-return)
argument-hint: <task_id> [model] [iterations]
allowed-tools: mcp__sunstead-control__dispatch_run, mcp__sunstead-control__get_task
---
Dispatch an optimization run using the **sunstead-control** MCP server.

Arguments: `$ARGUMENTS`
- `task_id` = `$1` (required)
- `model` = `$2` (optional; if omitted, call `get_task` for `$1` and use its `default_model`)
- `iterations` = `$3` (optional; default 10)

Steps:
1. If `$2` is empty, call the `get_task` tool with `task_id=$1` and read its `default_model`.
2. Call the `dispatch_run` tool with `task_id=$1`, the resolved model, and iterations.
3. Report the returned `run_id` and tell the operator they can poll progress with `/runs`.

Governance boundary: dispatching only **parameterizes** an existing active task — this is free. **Defining** a new task is governed (use `register_task`, which may escalate to `/escalations`). Never score, benchmark, or rank a run yourself — the frozen judge owns that.
