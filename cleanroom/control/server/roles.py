"""Postgres role-brokering for the remote control plane.

Deployment-grade requirement (the truth boundary). The serving process must NOT
connect to Postgres as a superuser, because a superuser bypasses every GRANT/REVOKE
— including the ones that wall off held-out / judge tables the optimizer must never
read or mutate. Instead the server logs in as a low-privilege *application* role and,
per request, ``SET ROLE``s into the role mapped from the authenticated caller's
claims (see ``cleanroom.control.server.auth``).

LEGITIMACY BOUNDARY: this is access control over *who may operate the plane*. It is
deliberately enforced one layer below the application, in Postgres itself, so that a
bug (or a compromised caller) in the operator surface still cannot cross a boundary
the database refuses to cross. It never touches the frozen pore/loss.

This module is intentionally DB-light so it unit-tests with a fake cursor and no live
database. The actual roles are created by ``sql/roles.sql``, applied out-of-band by
an admin — NOT by this server, and NOT auto-run against the shared Aiven service.
"""

from contextlib import contextmanager
import re

# The only roles the broker will ever SET ROLE into. Provisioned by sql/roles.sql.
# Anything outside this set is rejected before it can reach `SET ROLE`, so a bad
# claim can never widen its own privileges.
ROLE_READONLY = "sunstead_readonly"   # read the governance log / curves only
ROLE_OPERATOR = "sunstead_operator"   # dispatch runs, adjudicate escalations
ROLE_PROPOSER = "sunstead_proposer"   # the optimizer's role: write experiments, NO held-out
ROLE_ALLOWLIST = frozenset({ROLE_READONLY, ROLE_OPERATOR, ROLE_PROPOSER})

# Defence-in-depth: even an allowlisted name is re-checked against a strict ident
# grammar before interpolation, so this module can never emit an injection.
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


class RoleError(ValueError):
    """Raised when a role is not provisioned/allowed or the login is over-privileged."""


def validate_role(role: str) -> str:
    """Return `role` if it is an explicitly provisioned, syntactically safe role.

    Raises RoleError otherwise. The allowlist check comes first (intent), the ident
    grammar second (defence-in-depth against interpolation).
    """
    if role not in ROLE_ALLOWLIST:
        raise RoleError(f"role {role!r} is not provisioned (allowlist: {sorted(ROLE_ALLOWLIST)})")
    if not _IDENT_RE.match(role):  # unreachable for the constants above; guards future edits
        raise RoleError(f"role {role!r} is not a safe SQL identifier")
    return role


def apply_role(cursor, role: str) -> None:
    """`SET ROLE "<role>"` after validating it. The quotes + grammar make it injection-safe."""
    validate_role(role)
    cursor.execute(f'SET ROLE "{role}"')


def reset_role(cursor) -> None:
    """Drop back to the base application login."""
    cursor.execute("RESET ROLE")


@contextmanager
def role_scope(conn, role: str):
    """Run a block with the connection's effective role set to `role`, then reset.

    Pair this with a session-mode connection (or direct port, NOT a transaction-mode
    pooler) so the role does not leak across pooled transactions — see docs/deploy-aws.md.
    """
    validate_role(role)
    with conn.cursor() as cur:
        apply_role(cur, role)
    try:
        yield
    finally:
        with conn.cursor() as cur:
            reset_role(cur)


def assert_not_superuser(conn) -> None:
    """Startup guard: refuse to serve if the connection's login role is a superuser.

    A superuser silently bypasses every GRANT/REVOKE, so role-brokering would be
    theatre — the held-out tables would still be readable. We fail closed at boot
    rather than discover this in production.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        row = cur.fetchone()
    is_super = bool(row[0]) if row else False
    if is_super:
        raise RoleError(
            "refusing to serve: connected to Postgres as a SUPERUSER, which bypasses "
            "all GRANT/REVOKE and defeats the truth boundary. Point the serving process "
            "at CLEANROOM_PG_APP_DSN with a non-superuser login (see sql/roles.sql); keep "
            "the superuser DSN for migrations only."
        )
