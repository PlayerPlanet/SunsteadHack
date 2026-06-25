"""Per-request context shared between the HTTP transport and the MCP tools.

Kept in its own tiny module so both `mcp` (tools) and `runtime_app` (the AgentCore
identity middleware that sets the principal) can import it without an import cycle.

When `current_principal` is None — the local stdio mode, where a single trusted
operator runs the server as their own subprocess — tools skip scope enforcement.
When the HTTP middleware has authenticated a caller, it sets the principal and tools
enforce per-tool scope against it.
"""

from contextvars import ContextVar

from cleanroom.control.server.auth import Principal

current_principal: ContextVar[Principal | None] = ContextVar(
    "current_principal", default=None
)
