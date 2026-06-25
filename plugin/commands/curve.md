---
description: Show the p99 performance curve (experiments) for a task
argument-hint: <task_id>
allowed-tools: mcp__sunstead-control__read_curve
---
Call the `read_curve` tool on the **sunstead-control** MCP server with `task_id=$1` and present the experiment series as a curve.

For each experiment, show (in id order): the candidate `type`, `candidate_p99`, `within_noise`, and the `decision` (keep / discard / rollback / escalated). Summarize whether p99 is trending down.

You are **reading the frozen judge's log** — never recompute, re-score, or re-rank it yourself.
