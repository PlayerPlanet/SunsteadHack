"""Tests for the streamable-HTTP transport wrapper + bearer-auth middleware.

The FastMCP `/mcp` endpoint is replaced by a tiny mock ASGI app that records whether
it was reached and what principal was in context, so we test the transport/auth seam
in isolation (no real MCP session needed). Tokens are forged with a local RSA key.
"""

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from cleanroom.control.server.auth import (
    SCOPE_READ,
    OAuthResourceConfig,
    TokenValidator,
)
from cleanroom.control.server.context import current_principal
from cleanroom.control.server.http_app import build_app

ISSUER = "https://idp.example.com/"
AUDIENCE = "https://control.sunstead.example/mcp"
IAT, EXP = 1_700_000_000, 4_102_444_800

_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _PRIV.public_key()

# A mock MCP app that records the principal it saw, then replies 200.
_seen: dict = {}


async def _mock_mcp(scope, receive, send):
    _seen["principal"] = current_principal.get()
    resp = JSONResponse({"reached": True})
    await resp(scope, receive, send)


def _config():
    return OAuthResourceConfig(resource=AUDIENCE, issuer=ISSUER, audience=AUDIENCE,
                               authorization_servers=(ISSUER,))


def _token(**over):
    claims = {"sub": "u", "iss": ISSUER, "aud": AUDIENCE, "iat": IAT, "exp": EXP,
              "scope": SCOPE_READ}
    claims.update(over)
    return jwt.encode(claims, _PRIV, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def client():
    cfg = _config()
    validator = TokenValidator(cfg, key_resolver=lambda _t: _PUB)
    app = build_app(mcp_app=_mock_mcp, validator=validator, config=cfg, mcp_path="/mcp")
    _seen.clear()
    return TestClient(app)


def test_metadata_is_public(client):
    r = client.get("/.well-known/oauth-protected-resource")
    assert r.status_code == 200
    body = r.json()
    assert body["resource"] == AUDIENCE
    assert "control:dispatch" in body["scopes_supported"]


def test_health_is_public(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/livez").status_code == 204


def test_mcp_without_token_is_401_with_challenge(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    assert r.status_code == 401
    assert "resource_metadata=" in r.headers.get("WWW-Authenticate", "")
    assert _seen == {}  # never reached the MCP app


def test_mcp_with_bad_token_is_401(client):
    r = client.post("/mcp", headers={"Authorization": "Bearer not.a.jwt"},
                    json={"jsonrpc": "2.0"})
    assert r.status_code == 401
    assert "principal" not in _seen


def test_mcp_with_valid_token_reaches_app_with_principal(client):
    r = client.post("/mcp", headers={"Authorization": f"Bearer {_token()}"},
                    json={"jsonrpc": "2.0"})
    assert r.status_code == 200 and r.json() == {"reached": True}
    assert _seen["principal"] is not None
    assert _seen["principal"].subject == "u"
    assert SCOPE_READ in _seen["principal"].scopes


def test_principal_contextvar_is_reset_after_request(client):
    client.post("/mcp", headers={"Authorization": f"Bearer {_token()}"}, json={})
    # outside the request, the contextvar must be back to its default
    assert current_principal.get() is None


def test_insecure_mode_passes_through_without_token():
    # validator=None -> dev/insecure: the MCP app is reached unauthenticated.
    app = build_app(mcp_app=_mock_mcp, validator=None, config=None, mcp_path="/mcp")
    _seen.clear()
    c = TestClient(app)
    r = c.post("/mcp", json={})
    assert r.status_code == 200
    assert "principal" in _seen and _seen["principal"] is None
