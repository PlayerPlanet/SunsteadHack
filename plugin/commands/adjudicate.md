---
description: Record a human judgment on a governance escalation
argument-hint: <crossing_id> <approve|reject> [rationale]
allowed-tools: mcp__sunstead-control__adjudicate, mcp__sunstead-control__pending_escalations
---
Record a **human** judgment via the **sunstead-control** MCP server.

Arguments: `$ARGUMENTS`
- `crossing_id` = `$1`
- `decision` = `$2` (one of: approve, reject, allow, block)
- `rationale` = the remaining text after `$2`

This decision must reflect the operator's own judgment. If the decision is ambiguous or missing, ask the operator before acting — do not fabricate an approval. If helpful, call `pending_escalations` first to show what is being decided.

Then call the `adjudicate` tool with `crossing_id=$1`, `decision=$2`, the rationale, and `judge="human"`. An approve/allow on a `register_task` escalation activates the task. Report the outcome.
