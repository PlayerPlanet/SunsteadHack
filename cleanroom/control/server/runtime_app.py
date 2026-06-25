"""AgentCore Runtime serving app for the control-plane MCP server.

AgentCore Runtime hosts this FastMCP server and does inbound auth AT THE PLATFORM EDGE:
it validates the OAuth JWT against the IdP configured at `agentcore create`, and
returns 401 + the RFC 9728 protected-resource document itself. So — unlike the
self-hosted path — this app does NOT re-validate tokens or mint 401s. It only
EXTRACTS the caller's scopes/role from the forwarded token so per-tool authorization
(auth.TOOL_SCOPES via mcp._enforce) and DB-role brokering still apply.

SECURITY (read this): decode-without-verify is safe ONLY because AgentCore
authenticated the caller before forwarding the request. Never expose this app
directly to the internet without AgentCore (or an equivalent validating proxy) in
front — for that, use the validating self-hosted path instead. Regardless, the Aiven
non-superuser role-brokering (cleanroom.control.server.roles + sql/roles.sql) is the
hard backstop that holds even if this identity hint is missing or spoofed.

The server is exposed exactly as AgentCore expects: streamable-HTTP at 0.0.0.0:8000/mcp,
stateless_http=True.
"""

from __future__ import annotations

import logging

import jwt

from cleanroom.control.server.auth import principal_from_claims
from cleanroom.control.server.context import current_principal

logger = logging.getLogger(__name__)

# Claims-only decode: signature/aud/exp already enforced by AgentCore at the edge.
_DECODE_OPTS = {"verify_signature": False, "verify_aud": False, "verify_exp": False}


def _bearer(scope) -> str | None:
    for k, v in scope.get("headers", []):
        if k == b"authorization":
            val = v.decode("latin-1")
            if val.lower().startswith("bearer "):
                return val[7:].strip()
    return None


def principal_from_token(token: str):
    """Decode (do NOT verify) a forwarded bearer token into a Principal, or None."""
    try:
        claims = jwt.decode(token, options=_DECODE_OPTS)
    except jwt.PyJWTError as exc:
        logger.warning("could not decode forwarded token for identity hint: %s", exc)
        return None
    # Non-strict: an odd/over-asking role claim falls back to least privilege rather
    # than erroring — AgentCore already decided the caller may be here at all.
    return principal_from_claims(claims, strict_role=False)


class IdentityMiddleware:
    """Pure-ASGI: set current_principal from the forwarded token, then pass through.

    Never short-circuits (no 401/403) — AgentCore owns inbound auth responses. If no
    usable token is forwarded, the request proceeds with no principal, and per-tool
    scope enforcement no-ops (same as stdio/local).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _bearer(scope)
        principal = principal_from_token(token) if token else None
        if principal is None:
            await self.app(scope, receive, send)
            return
        tok = current_principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            current_principal.reset(tok)


def build_runtime_app(*, host: str = "0.0.0.0", port: int = 8000):
    """Build the AgentCore-ready ASGI app: FastMCP streamable-HTTP /mcp + identity hint.

    Returns the wrapped ASGI app. AgentCore expects it served at host:port/mcp.
    """
    from cleanroom.control.server.mcp import build_server

    server = build_server()
    server.settings.stateless_http = True   # AgentCore default for basic MCP servers
    server.settings.host = host
    server.settings.port = port
    return IdentityMiddleware(server.streamable_http_app())
