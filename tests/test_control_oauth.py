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
from cleanroom.control.server.auth import principal_from_claims
from cleanroom.control.server.roles import ROLE_OPERATOR, ROLE_PROPOSER, ROLE_READONLY

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


# ---- group-driven role + role-implied scopes (dashboard registration path) -----
# These exercise principal_from_claims directly the way the AgentCore runtime middleware
# does (decoded claims, strict_role=False), since that is where dashboard tokens land.

def test_cognito_group_maps_to_operator_role_and_scopes():
    # A user registered on the dashboard and put in the operators group. Their access
    # token carries only openid/email + cognito:groups — no control:* scopes.
    p = principal_from_claims(
        {"sub": "u", "scope": "openid email", "cognito:groups": ["sunstead-operators"]},
        strict_role=False,
    )
    assert p.db_role == ROLE_OPERATOR
    # role implies the operator scope surface, so group membership alone authorizes.
    assert {"control:read", "control:dispatch", "control:adjudicate"} <= p.scopes


def test_no_group_defaults_to_readonly_with_read_scope():
    p = principal_from_claims(
        {"sub": "u", "scope": "openid email"}, strict_role=False
    )
    assert p.db_role == ROLE_READONLY
    assert p.scopes == frozenset({"control:read"})  # can read, cannot mutate
    authorize_tool(p, "read_boundary")
    with pytest.raises(AuthError):
        authorize_tool(p, "dispatch_run")


def test_multiple_groups_take_highest_privilege():
    p = principal_from_claims(
        {"sub": "u", "cognito:groups": ["sunstead-viewers", "sunstead-operators"]},
        strict_role=False,
    )
    assert p.db_role == ROLE_OPERATOR


def test_proposer_group_maps_to_proposer_role():
    p = principal_from_claims(
        {"sub": "u", "cognito:groups": ["sunstead-proposers"]}, strict_role=False
    )
    assert p.db_role == ROLE_PROPOSER
    assert p.scopes == frozenset({"control:read", "control:register"})


def test_explicit_db_role_claim_beats_group():
    # A pre-token Lambda (or machine caller) naming db_role wins over group inference.
    p = principal_from_claims(
        {"sub": "u", "db_role": ROLE_READONLY, "cognito:groups": ["sunstead-operators"]},
        strict_role=False,
    )
    assert p.db_role == ROLE_READONLY


def test_machine_precise_control_scopes_are_preserved():
    # A client_credentials caller presenting exact control:* scopes keeps only those,
    # even though its role would imply more — least privilege for automation.
    p = principal_from_claims(
        {"sub": "svc", "scope": "control:read", "cognito:groups": ["sunstead-operators"]},
        strict_role=False,
    )
    assert p.db_role == ROLE_OPERATOR
    assert p.scopes == frozenset({"control:read"})  # NOT widened to the operator set


def test_resource_server_scope_prefix_is_normalized():
    # Cognito qualifies resource-server scopes: "<resource-id>/control:dispatch".
    p = principal_from_claims(
        {"sub": "svc", "scope": "sunstead-control/control:read sunstead-control/control:dispatch"},
        strict_role=False,
    )
    assert {"control:read", "control:dispatch"} == p.scopes


def test_from_env_requires_core_settings():
    with pytest.raises(ValueError):
        OAuthResourceConfig.from_env({})
    cfg = OAuthResourceConfig.from_env(
        {"OAUTH_ISSUER": ISSUER, "OAUTH_AUDIENCE": AUDIENCE}
    )
    assert cfg.issuer == ISSUER and cfg.audience == AUDIENCE
