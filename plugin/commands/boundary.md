---
description: Show the boundary instrument — the manifesto's two live readings
allowed-tools: mcp__sunstead-control__read_boundary
---
Call the `read_boundary` tool on the **sunstead-control** MCP server and present the two readings drawn off the escalation log:

- **Spatial** (`spatial`: escalation rate vs `drift_level`) — where the autonomous edge is *now*. As workload drifts from what the system has earned trust on, escalation rate should rise.
- **Longitudinal** (`longitudinal`: escalations-per-unit-work vs cumulative volume) — whether the frontier recedes. With the **frozen** pore this line is **flat by design** — and that flatness is the point: the frontier that does not *yet* recede.

Always surface the `proxy_caveat`: the pore gates blast-radius + reversibility, a **lower bound on, not identical to**, the agent's true epistemic edge. Never present the proxy as the true boundary. This is read-only — do not recompute or re-score.
