---
description: List governance escalations awaiting human judgment
allowed-tools: mcp__sunstead-control__pending_escalations
---
Call the `pending_escalations` tool on the **sunstead-control** MCP server and present each pending crossing: its `id`, the `pore` rule that fired, `risk_level`, and the proposed `action` (e.g. a `register_task` definition).

For each crossing, tell the operator they can resolve it with `/adjudicate <crossing_id> approve|reject [rationale]`.

These are **human** decisions. Do not auto-approve or invent a verdict — surface the escalations and wait for the operator.
