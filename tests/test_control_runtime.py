"""Tests for the AgentCore Runtime serving path (identity extraction, not validation).

AgentCore validates the JWT at the edge, so the runtime app only DECODES the forwarded
token to recover scopes/role for per-tool authorization. These tests forge tokens with
an HS key and decode-without-verify, mirroring that trust boundary.
"""

import jwt
import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from cleanroom.control.server.auth import SCOPE_READ
from cleanroom.control.server.context import current_principal
from cleanroom.control.server.roles import ROLE_OPERATOR, ROLE_READONLY
from cleanroom.control.server.runtime_app import (
    IdentityMiddleware,
    principal_from_token,
)

# Tokens are never verified here (AgentCore did that), so any key/alg works.
_seen: dict = {}


def _tok(**claims) -> str:
    base = {"sub": "u", "scope": SCOPE_READ}
    base.update(claims)
    return jwt.encode(base, "x" * 32, algorithm="HS256")  # key irrelevant; never verified


# ---- decode-only principal extraction ---------------------------------------

def test_principal_from_token_extracts_scopes():
    p = principal_from_token(_tok(scope="control:read control:dispatch"))
    assert p is not None
    assert p.subject == "u"
    assert p.scopes == frozenset({"control:read", "control:dispatch"})
    assert p.db_role == ROLE_READONLY  # no role claim -> least privilege


def test_principal_from_token_honors_provisioned_role_claim():
    p = principal_from_token(_tok(db_role=ROLE_OPERATOR))
    assert p.db_role == ROLE_OPERATOR


def test_principal_from_token_falls_back_on_unprovisioned_role():
    # Non-strict at the runtime edge: an over-asking role claim degrades to least
    # privilege rather than raising (AgentCore already authenticated the caller).
    p = principal_from_token(_tok(db_role="postgres"))
    assert p.db_role == ROLE_READONLY


def test_principal_from_token_handles_garbage():
    assert principal_from_token("not-a-jwt") is None


# ---- identity middleware over a mock MCP app --------------------------------

async def _mock_mcp(scope, receive, send):
    _seen["principal"] = current_principal.get()
    await JSONResponse({"reached": True})(scope, receive, send)


@pytest.fixture
def client():
    _seen.clear()
    return TestClient(IdentityMiddleware(_mock_mcp))


def test_forwarded_token_sets_principal(client):
    r = client.post("/mcp", headers={"Authorization": f"Bearer {_tok(scope=SCOPE_READ)}"}, json={})
    assert r.status_code == 200
    assert _seen["principal"] is not None
    assert SCOPE_READ in _seen["principal"].scopes


def test_no_token_passes_through_without_principal(client):
    # AgentCore owns 401s; the app never blocks. Missing token -> no principal.
    r = client.post("/mcp", json={})
    assert r.status_code == 200
    assert _seen["principal"] is None


def test_principal_contextvar_reset_after_request(client):
    client.post("/mcp", headers={"Authorization": f"Bearer {_tok()}"}, json={})
    assert current_principal.get() is None


# ---- per-tool scope still enforced under the runtime path -------------------

def test_tool_scope_enforced_from_forwarded_identity():
    from cleanroom.control.server import mcp as mcpmod
    from cleanroom.control.server.auth import AuthError

    p = principal_from_token(_tok(scope="control:read"))  # read only
    tok = current_principal.set(p)
    try:
        with pytest.raises(AuthError):
            mcpmod.tool_dispatch_run("t", "m", 1)  # needs control:dispatch
    finally:
        current_principal.reset(tok)


# ---- the runtime app builds with the AgentCore contract ---------------------

def test_build_runtime_app_serves_mcp_stateless():
    from cleanroom.control.server.runtime_app import build_runtime_app

    app = build_runtime_app()
    assert isinstance(app, IdentityMiddleware)
    # the wrapped MCP app is the FastMCP streamable-http ASGI app
    assert app.app is not None
