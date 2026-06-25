"""OAuth 2.1 Resource Server for the control-plane MCP server.

This makes the remote MCP server a *Resource Server* in the OAuth 2.1 sense (the MCP
authorization spec references RFC 9728 protected-resource metadata and RFC 8707
resource indicators). It does NOT issue tokens — an external Authorization Server / IdP
you control (e.g. AWS Cognito; see infra/terraform/cognito.tf) does that. Here we only:

  * publish protected-resource metadata so a client can discover the AS,
  * validate the bearer access token per request (RS256 signature against the AS's
    JWKS, plus issuer / audience / expiry / required claims),
  * map verified claims to a Principal carrying the caller's scopes and the Postgres
    role the request must run under (brokered in cleanroom.control.server.roles).

LEGITIMACY BOUNDARY: auth decides *who may operate the control plane*, never *what the
frozen judge scores*. Scopes gate operator tools (dispatch/adjudicate); they never
touch pore or loss.

Testability: TokenValidator takes an injectable `key_resolver`, so tests forge RS256
tokens with a locally generated keypair — no network, no real IdP. In production
`make_jwks_key_resolver` wires PyJWKClient against the AS's JWKS endpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

import jwt

from cleanroom.control.server.roles import (
    ROLE_ALLOWLIST,
    ROLE_OPERATOR,
    ROLE_READONLY,
    RoleError,
    validate_role,
)

# ---- Scopes (the operator surface, gated; never the judge) ------------------
SCOPE_READ = "control:read"          # list tasks/runs, read curves + boundary
SCOPE_REGISTER = "control:register"  # register a task (still governance-gated by the pore)
SCOPE_DISPATCH = "control:dispatch"  # dispatch / cancel runs
SCOPE_ADJUDICATE = "control:adjudicate"  # write human judgments on escalations
ALL_SCOPES = (SCOPE_READ, SCOPE_REGISTER, SCOPE_DISPATCH, SCOPE_ADJUDICATE)

# Which scope each MCP tool requires. Reads are cheap; mutations escalate.
TOOL_SCOPES: dict[str, str] = {
    "list_tasks": SCOPE_READ,
    "get_task": SCOPE_READ,
    "get_run": SCOPE_READ,
    "list_runs": SCOPE_READ,
    "read_curve": SCOPE_READ,
    "read_boundary": SCOPE_READ,
    "pending_escalations": SCOPE_READ,
    "register_task": SCOPE_REGISTER,
    "dispatch_run": SCOPE_DISPATCH,
    "cancel_run": SCOPE_DISPATCH,
    "adjudicate": SCOPE_ADJUDICATE,
}


class AuthError(Exception):
    """An authentication/authorization failure carrying an HTTP status + OAuth error code."""

    def __init__(self, status: int, error: str, description: str, *, scope: str | None = None):
        super().__init__(description)
        self.status = status          # 401 (no/invalid token) or 403 (insufficient scope)
        self.error = error            # OAuth error code, e.g. "invalid_token"
        self.description = description
        self.scope = scope            # required scope, for insufficient_scope challenges


@dataclass(frozen=True, slots=True)
class Principal:
    """A verified caller. Immutable; carries exactly what downstream needs to decide."""

    subject: str
    tenant: str | None
    scopes: frozenset[str]
    db_role: str
    claims: dict = field(default_factory=dict, repr=False)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


@dataclass(frozen=True, slots=True)
class OAuthResourceConfig:
    """Static config for this resource server. Built from env in production."""

    resource: str                       # canonical URI of this MCP server (the audience)
    issuer: str                         # expected `iss`
    audience: str                       # expected `aud` (usually == resource)
    authorization_servers: tuple[str, ...] = ()
    jwks_uri: str | None = None
    algorithms: tuple[str, ...] = ("RS256",)
    # Claim names (Cognito/Auth0-shaped defaults; override per IdP).
    scopes_claim: str = "scope"         # space-delimited string OR list; "scp" also honored
    tenant_claim: str = "tenant"
    role_claim: str = "db_role"         # an explicit role claim, if the AS emits one
    # tenant -> Postgres role; used when no explicit role_claim is present.
    role_map: dict[str, str] = field(default_factory=dict)
    default_role: str = ROLE_READONLY   # least privilege when nothing else matches

    @classmethod
    def from_env(cls, env: dict | None = None) -> "OAuthResourceConfig":
        e = env if env is not None else os.environ
        resource = e.get("OAUTH_RESOURCE") or e.get("OAUTH_AUDIENCE", "")
        issuer = e.get("OAUTH_ISSUER", "")
        audience = e.get("OAUTH_AUDIENCE") or resource
        if not (resource and issuer and audience):
            raise ValueError(
                "OAuth not configured: set OAUTH_ISSUER, OAUTH_AUDIENCE (and optionally "
                "OAUTH_RESOURCE, OAUTH_JWKS_URI). For the offline/dev server use the "
                "in-process validator instead."
            )
        return cls(
            resource=resource,
            issuer=issuer,
            audience=audience,
            authorization_servers=tuple(
                s for s in (e.get("OAUTH_AUTH_SERVERS", issuer).split(",")) if s
            ),
            jwks_uri=e.get("OAUTH_JWKS_URI"),
            scopes_claim=e.get("OAUTH_SCOPES_CLAIM", "scope"),
            tenant_claim=e.get("OAUTH_TENANT_CLAIM", "tenant"),
            role_claim=e.get("OAUTH_ROLE_CLAIM", "db_role"),
            default_role=e.get("OAUTH_DEFAULT_ROLE", ROLE_READONLY),
        )

    # ---- RFC 9728 protected-resource metadata -------------------------------
    @property
    def metadata_path(self) -> str:
        return "/.well-known/oauth-protected-resource"

    def protected_resource_metadata(self) -> dict:
        return {
            "resource": self.resource,
            "authorization_servers": list(self.authorization_servers),
            "scopes_supported": list(ALL_SCOPES),
            "bearer_methods_supported": ["header"],
        }

    def challenge(self, *, error: str | None = None, description: str | None = None,
                  scope: str | None = None) -> str:
        """The WWW-Authenticate header value, pointing clients at the metadata doc."""
        md_url = self.resource.rstrip("/") + self.metadata_path
        parts = [f'Bearer resource_metadata="{md_url}"']
        if error:
            parts.append(f'error="{error}"')
        if description:
            parts.append(f'error_description="{description}"')
        if scope:
            parts.append(f'scope="{scope}"')
        return ", ".join(parts)


# Resolves the verification key for a given encoded token (by its `kid` header).
KeyResolver = Callable[[str], object]


def make_jwks_key_resolver(jwks_uri: str) -> KeyResolver:
    """Production resolver: fetch + cache signing keys from the AS's JWKS endpoint."""
    client = jwt.PyJWKClient(jwks_uri)

    def _resolve(token: str):
        return client.get_signing_key_from_jwt(token).key

    return _resolve


class TokenValidator:
    """Validates bearer access tokens and produces a Principal."""

    def __init__(self, config: OAuthResourceConfig, *, key_resolver: KeyResolver):
        self.config = config
        self._resolve_key = key_resolver

    def validate(self, token: str) -> Principal:
        cfg = self.config
        try:
            key = self._resolve_key(token)
        except Exception as exc:  # JWKS miss, malformed header, etc.
            raise AuthError(401, "invalid_token", f"cannot resolve signing key: {exc}") from exc

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=list(cfg.algorithms),
                audience=cfg.audience,
                issuer=cfg.issuer,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError(401, "invalid_token", "token expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthError(401, "invalid_token", "wrong audience") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthError(401, "invalid_token", "wrong issuer") from exc
        except jwt.PyJWTError as exc:
            raise AuthError(401, "invalid_token", f"invalid token: {exc}") from exc

        return self._principal(claims)

    def _principal(self, claims: dict) -> Principal:
        cfg = self.config
        return principal_from_claims(
            claims,
            scopes_claim=cfg.scopes_claim,
            tenant_claim=cfg.tenant_claim,
            role_claim=cfg.role_claim,
            role_map=cfg.role_map,
            default_role=cfg.default_role,
            strict_role=True,
        )


def principal_from_claims(
    claims: dict, *, scopes_claim: str = "scope", tenant_claim: str = "tenant",
    role_claim: str = "db_role", role_map: dict | None = None,
    default_role: str = ROLE_READONLY, strict_role: bool = True,
) -> Principal:
    """Map already-decoded JWT claims to a Principal.

    Shared by TokenValidator (which decodes+verifies the token) and the AgentCore
    identity-extraction middleware (which trusts the platform's verification and only
    decodes). `strict_role=True` rejects an unprovisioned role claim (the validator
    path); `strict_role=False` falls back to least privilege instead of erroring (the
    runtime path, where AgentCore has already authenticated the caller).
    """
    role_map = role_map or {}
    scopes = _extract_scopes(claims, scopes_claim)
    tenant = claims.get(tenant_claim) or claims.get("client_id") or claims.get("azp")
    raw = claims.get(role_claim)
    if raw:
        try:
            db_role = validate_role(raw)
        except RoleError as exc:
            if strict_role:
                # A claim asking for a non-provisioned role is a hard auth failure,
                # not a silent downgrade — surfacing it beats quietly over-granting.
                raise AuthError(403, "insufficient_scope", str(exc)) from exc
            db_role = validate_role(default_role)
    elif tenant and tenant in role_map:
        db_role = validate_role(role_map[tenant])
    else:
        db_role = validate_role(default_role)
    return Principal(
        subject=claims.get("sub") or "unknown",
        tenant=tenant,
        scopes=frozenset(scopes),
        db_role=db_role,
        claims=claims,
    )


def _extract_scopes(claims: dict, scopes_claim: str) -> set[str]:
    val = claims.get(scopes_claim)
    if val is None:
        val = claims.get("scp")  # Azure/Cognito sometimes use "scp"
    if val is None:
        return set()
    if isinstance(val, str):
        return {s for s in val.split() if s}
    if isinstance(val, (list, tuple)):
        return {str(s) for s in val}
    return set()


def authorize(principal: Principal, required_scope: str) -> None:
    """Raise AuthError(403) unless the principal holds the required scope."""
    if not principal.has_scope(required_scope):
        raise AuthError(
            403, "insufficient_scope",
            f"this operation requires scope {required_scope!r}",
            scope=required_scope,
        )


def authorize_tool(principal: Principal, tool_name: str) -> None:
    """Authorize an MCP tool call by its registered scope requirement."""
    required = TOOL_SCOPES.get(tool_name)
    if required is None:
        # Unknown tool -> fail closed.
        raise AuthError(403, "insufficient_scope", f"unknown tool {tool_name!r}")
    authorize(principal, required)


__all__ = [
    "AuthError", "Principal", "OAuthResourceConfig", "TokenValidator",
    "make_jwks_key_resolver", "authorize", "authorize_tool", "principal_from_claims",
    "SCOPE_READ", "SCOPE_REGISTER", "SCOPE_DISPATCH", "SCOPE_ADJUDICATE",
    "ALL_SCOPES", "TOOL_SCOPES",
    "ROLE_ALLOWLIST", "ROLE_OPERATOR", "ROLE_READONLY",
]
