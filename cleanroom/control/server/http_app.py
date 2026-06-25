"""Streamable-HTTP transport for the control-plane MCP server + OAuth enforcement.

The stdio server (cleanroom.control.server.mcp.main) stays the local plugin-subprocess
path. This module is what lets a *remote* Claude plugin reach an AWS deployment: it
wraps FastMCP's streamable_http_app() (the `/mcp` ASGI endpoint) in a parent Starlette
app that

  * serves /.well-known/oauth-protected-resource (RFC 9728) and /healthz UNAUTHENTICATED,
  * validates the bearer access token on the MCP path via the OAuth resource server
    (auth.TokenValidator), returning 401 + a WWW-Authenticate challenge that points
    clients at the metadata document,
  * stashes the verified Principal in a contextvar (context.current_principal) so the
    MCP tools enforce per-tool scope and broker the Postgres role.

Run it with `python -m cleanroom.control.server.http` (main_http below) or any ASGI
server pointed at `build_default_app()`.
"""

from __future__ import annotations

import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from cleanroom.control.server.auth import (
    AuthError,
    OAuthResourceConfig,
    TokenValidator,
    make_jwks_key_resolver,
)
from cleanroom.control.server.context import current_principal

DEFAULT_MCP_PATH = "/mcp"


class BearerAuthMiddleware:
    """Pure-ASGI middleware: enforce a valid bearer token on the protected prefix.

    Public paths (metadata, health) and CORS preflight pass straight through. On the
    protected prefix a missing/invalid token yields 401 with a WWW-Authenticate
    challenge; a valid token sets `current_principal` for the duration of the request.

    If `validator` is None the middleware is a pass-through (insecure dev mode); the
    HTTP entrypoint only allows that when CLEANROOM_ALLOW_INSECURE is set.
    """

    def __init__(self, app, *, validator: TokenValidator | None,
                 config: OAuthResourceConfig | None, protected_prefix: str = DEFAULT_MCP_PATH):
        self.app = app
        self.validator = validator
        self.config = config
        self.protected_prefix = protected_prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.validator is None:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")
        if method == "OPTIONS" or not path.startswith(self.protected_prefix):
            await self.app(scope, receive, send)
            return

        token = _bearer_token(scope)
        if not token:
            await self._reject(scope, receive, send,
                               AuthError(401, "invalid_request", "missing bearer token"))
            return
        try:
            principal = self.validator.validate(token)
        except AuthError as exc:
            await self._reject(scope, receive, send, exc)
            return

        tok = current_principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            current_principal.reset(tok)

    async def _reject(self, scope, receive, send, exc: AuthError):
        headers = {}
        if self.config is not None:
            headers["WWW-Authenticate"] = self.config.challenge(
                error=exc.error, description=exc.description, scope=exc.scope
            )
        resp = JSONResponse(
            {"error": exc.error, "error_description": exc.description},
            status_code=exc.status,
            headers=headers,
        )
        await resp(scope, receive, send)


def _bearer_token(scope) -> str | None:
    for k, v in scope.get("headers", []):
        if k == b"authorization":
            val = v.decode("latin-1")
            if val.lower().startswith("bearer "):
                return val[7:].strip()
    return None


def build_app(*, mcp_app, validator: TokenValidator | None,
              config: OAuthResourceConfig | None, mcp_path: str = DEFAULT_MCP_PATH) -> Starlette:
    """Compose the parent ASGI app: public metadata/health routes + the guarded MCP mount."""

    async def metadata(_request: Request):
        if config is None:
            return JSONResponse({"error": "oauth_not_configured"}, status_code=404)
        return JSONResponse(config.protected_resource_metadata())

    async def healthz(_request: Request):
        return JSONResponse({"status": "ok"})

    async def livez(_request: Request):
        return Response(status_code=204)

    routes = [
        Route("/.well-known/oauth-protected-resource", metadata, methods=["GET"]),
        Route("/healthz", healthz, methods=["GET"]),
        Route("/livez", livez, methods=["GET"]),
        Mount(mcp_path, app=mcp_app),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(BearerAuthMiddleware, validator=validator, config=config,
                       protected_prefix=mcp_path)
    return app


def build_default_app() -> Starlette:
    """Build the production app from env, enforcing the serving guards.

    Requires OAuth config (OAUTH_ISSUER/OAUTH_AUDIENCE/OAUTH_JWKS_URI) unless
    CLEANROOM_ALLOW_INSECURE is set (dev only — disables auth entirely).
    """
    from cleanroom.control.server.mcp import build_server
    from cleanroom.control.server.wiring import assert_serving_safe

    # Fail fast if the serving DB login is a superuser (truth-boundary guard).
    assert_serving_safe()

    server = build_server()
    mcp_path = os.environ.get("CLEANROOM_MCP_PATH", DEFAULT_MCP_PATH)
    server.settings.streamable_http_path = mcp_path
    mcp_app = server.streamable_http_app()

    if os.environ.get("CLEANROOM_ALLOW_INSECURE"):
        # Dev only: no token enforcement. Loudly unauthenticated.
        return build_app(mcp_app=mcp_app, validator=None, config=None, mcp_path=mcp_path)

    config = OAuthResourceConfig.from_env()
    if not config.jwks_uri:
        raise ValueError("OAUTH_JWKS_URI is required to validate tokens in production")
    validator = TokenValidator(config, key_resolver=make_jwks_key_resolver(config.jwks_uri))
    return build_app(mcp_app=mcp_app, validator=validator, config=config, mcp_path=mcp_path)


def main_http(argv=None) -> int:
    """Entrypoint: serve the control plane over streamable HTTP (uvicorn)."""
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(build_default_app(), host=host, port=port, log_level=os.environ.get("LOG_LEVEL", "info"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_http())
