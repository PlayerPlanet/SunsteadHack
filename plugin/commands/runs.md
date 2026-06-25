---
description: List runs, or show one run's status, for the control plane
argument-hint: [run_id]
allowed-tools: mcp__sunstead-control__list_runs, mcp__sunstead-control__get_run
---
Show optimization run status from the **sunstead-control** MCP server.

Arguments: `$ARGUMENTS`
- If a `run_id` (`$1`) is given, call the `get_run` tool and present its `state`, `iterations_done`, `best_p99`, `started_at`/`ended_at`, and any `error_msg`.
- Otherwise call the `list_runs` tool and present a compact table of all runs: `run_id`, `task_id`, `state`, `iterations_done`, `best_p99`.

This is read-only proprioception — just report what the store returns.
