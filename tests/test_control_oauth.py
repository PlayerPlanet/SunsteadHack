"""Unit tests for the OAuth 2.1 resource server — forged RS256 tokens, no network.

A locally generated RSA keypair stands in for the IdP's signing key; the key_resolver
just returns its public key, so token validation runs fully offline and deterministic.
"""

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from cleanroom.control.server.auth import (
    SCOPE_DISPATCH,
    SCOPE_READ,
    AuthError,
    OAuthResourceConfig,
    TokenValidator,
    authorize,
    authorize_tool,
)
from cleanroom.control.server.roles import ROLE_OPERATOR, ROLE_READONLY

ISSUER = "https://idp.example.com/"
AUDIENCE = "https://control.sunstead.example/mcp"

# Deterministic, real-clock-relative timestamps: far future stays valid, the past
# stays expired, regardless of when the suite runs.
IAT = 1_700_000_000
EXP_FUTURE = 4_102_444_800   # ~year 2100
EXP_PAST = 1_600_000_000     # ~2020

_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _PRIV.public_key()
_OTHER_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _config(**over) -> OAuthResourceConfig:
    base = dict(resource=AUDIENCE, issuer=ISSUER, audience=AUDIENCE,
                authorization_servers=(ISSUER,), default_role=ROLE_READONLY)
    base.update(over)
    return OAuthResourceConfig(**base)


def _token(signing_key=_PRIV, **claim_over) -> str:
    claims = {"sub": "user-1", "iss": ISSUER, "aud": AUDIENCE,
              "iat": IAT, "exp": EXP_FUTURE, "scope": SCOPE_READ}
    claims.update(claim_over)
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "k1"})


def _validator(config=None) -> TokenValidator:
    return TokenValidator(config or _config(), key_resolver=lambda _t: _PUB)


# ---- happy path -------------------------------------------------------------

def test_valid_token_yields_principal():
    p = _validator().validate(_token(scope="control:read control:dispatch"))
    assert p.subject == "user-1"
    assert p.scopes == frozenset({"control:read", "control:dispatch"})
    assert p.db_role == ROLE_READONLY  # no role claim / tenant -> least privilege


def test_scopes_from_scp_list_claim():
    cfg = _config()
    # drop the default "scope" string, provide "scp" list instead
    tok = _token(scope=None, scp=["control:read", "control:adjudicate"])
    p = TokenValidator(cfg, key_resolver=lambda _t: _PUB).validate(tok)
    assert "control:adjudicate" in p.scopes


# ---- rejection paths --------------------------------------------------------

def test_wrong_audience_rejected():
    with pytest.raises(AuthError) as ei:
        _validator().validate(_token(aud="https://evil.example/"))
    assert ei.value.status == 401 and ei.value.error == "invalid_token"


def test_wrong_issuer_rejected():
    with pytest.raises(AuthError) as ei:
        _validator().validate(_token(iss="https://evil-idp.example/"))
    assert ei.value.status == 401


def test_expired_token_rejected():
    with pytest.raises(AuthError) as ei:
        _validator().validate(_token(exp=EXP_PAST))
    assert ei.value.status == 401 and "expired" in ei.value.description


def test_bad_signature_rejected():
    # signed by a different key than the resolver returns
    with pytest.raises(AuthError) as ei:
        _validator().validate(_token(signing_key=_OTHER_PRIV))
    assert ei.value.status == 401


def test_missing_required_claim_rejected():
    with pytest.raises(AuthError) as ei:
        _validator().validate(_token(exp=None))  # require: exp
    assert ei.value.status == 401


def test_key_resolution_failure_is_401():
    def boom(_t):
        raise RuntimeError("jwks down")

    v = TokenValidator(_config(), key_resolver=boom)
    with pytest.raises(AuthError) as ei:
        v.validate(_token())
    assert ei.value.status == 401


# ---- role brokering via claims ---------------------------------------------

def test_explicit_provisioned_role_claim_used():
    p = _validator().validate(_token(db_role=ROLE_OPERATOR))
    assert p.db_role == ROLE_OPERATOR


def test_unprovisioned_role_claim_is_forbidden():
    with pytest.raises(AuthError) as ei:
        _validator().validate(_token(db_role="postgres"))
    assert ei.value.status == 403  # never silently downgrade an over-ask


def test_tenant_role_map_resolves_role():
    cfg = _config(role_map={"team-a": ROLE_OPERATOR})
    v = TokenValidator(cfg, key_resolver=lambda _t: _PUB)
    p = v.validate(_token(tenant="team-a"))
    assert p.db_role == ROLE_OPERATOR
    assert p.tenant == "team-a"


# ---- scope authorization ----------------------------------------------------

def test_authorize_passes_with_scope():
    p = _validator().validate(_token(scope=SCOPE_DISPATCH))
    authorize(p, SCOPE_DISPATCH)  # no raise


def test_authorize_raises_insufficient_scope():
    p = _validator().validate(_token(scope=SCOPE_READ))
    with pytest.raises(AuthError) as ei:
        authorize(p, SCOPE_DISPATCH)
    assert ei.value.status == 403 and ei.value.scope == SCOPE_DISPATCH


def test_authorize_tool_maps_tool_to_scope():
    reader = _validator().validate(_token(scope=SCOPE_READ))
    authorize_tool(reader, "read_curve")  # read scope ok
    with pytest.raises(AuthError):
        authorize_tool(reader, "dispatch_run")  # needs dispatch scope


def test_authorize_tool_unknown_tool_fails_closed():
    p = _validator().validate(_token(scope="control:read control:dispatch control:adjudicate"))
    with pytest.raises(AuthError):
        authorize_tool(p, "drop_database")


# ---- metadata + challenge ---------------------------------------------------

def test_protected_resource_metadata_shape():
    md = _config().protected_resource_metadata()
    assert md["resource"] == AUDIENCE
    assert ISSUER in md["authorization_servers"]
    assert "control:dispatch" in md["scopes_supported"]
    assert md["bearer_methods_supported"] == ["header"]


def test_challenge_header_points_at_metadata():
    ch = _config().challenge(error="invalid_token", description="token expired")
    assert "resource_metadata=" in ch
    assert ".well-known/oauth-protected-resource" in ch
    assert 'error="invalid_token"' in ch


def test_from_env_requires_core_settings():
    with pytest.raises(ValueError):
        OAuthResourceConfig.from_env({})
    cfg = OAuthResourceConfig.from_env(
        {"OAUTH_ISSUER": ISSUER, "OAUTH_AUDIENCE": AUDIENCE}
    )
    assert cfg.issuer == ISSUER and cfg.audience == AUDIENCE
