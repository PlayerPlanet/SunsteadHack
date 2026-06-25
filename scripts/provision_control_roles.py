#!/usr/bin/env python
"""Provision (or rotate) the AgentCore control-plane DB + non-superuser brokered roles.

Runs the substance of sql/roles.sql against a dedicated `sunstead_control` database on
the target service: schema (cleanroom/db/schema.sql), the brokered roles, and the
GRANT/REVOKE that wall off least privilege. Idempotent — re-running resets the
`sunstead_app` password (i.e. this IS the rotation tool) and completes a partial run.

  ADMIN_DSN='postgresql://avnadmin:...@host:11244/defaultdb?sslmode=require' \
      python scripts/provision_control_roles.py

SECRET HANDLING: the new app password is NEVER printed. The full app DSN is written to
a gitignored file (default: app_dsn.secret, override with APP_DSN_OUT) and stdout shows
only a masked line. Copy the DSN from that file into your secret store, then delete it.
Pass APP_PWD to choose the password yourself instead of generating one.
"""
import os
import re
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

NEW_DB = "sunstead_control"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "cleanroom" / "db" / "schema.sql"
BROKERED = ["sunstead_readonly", "sunstead_operator", "sunstead_proposer"]
_TRANSIENT = ("getaddrinfo", "could not translate host", "could not connect",
              "connection refused", "timeout", "temporarily unavailable")


def connect(dsn: str, **kw):
    """psycopg.connect, retrying ONLY transient DNS/network blips (not auth failures)."""
    last = None
    for attempt in range(5):
        try:
            return psycopg.connect(dsn, **kw)
        except psycopg.OperationalError as exc:
            if not any(t in str(exc).lower() for t in _TRANSIENT):
                raise
            last = exc
            print(f"[retry] connect attempt {attempt + 1} failed; retrying...", file=sys.stderr)
            time.sleep(2)
    raise last


def with_db(dsn: str, dbname: str) -> str:
    p = urlsplit(dsn)
    return urlunsplit((p.scheme, p.netloc, "/" + dbname, p.query, p.fragment))


def role_exists(cur, name: str) -> bool:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,))
    return cur.fetchone() is not None


def main() -> int:
    admin_dsn = os.environ.get("ADMIN_DSN")
    if not admin_dsn:
        print("ERROR: set ADMIN_DSN to the avnadmin DSN (…/defaultdb?sslmode=require).",
              file=sys.stderr)
        return 2
    app_pwd = os.environ.get("APP_PWD") or secrets.token_urlsafe(24)
    out_path = Path(os.environ.get("APP_DSN_OUT", "app_dsn.secret"))

    # 1) Dedicated database (autocommit; CREATE DATABASE can't run in a txn).
    with connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (NEW_DB,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(NEW_DB)))
            print(f"[db] created {NEW_DB}")
        else:
            print(f"[db] {NEW_DB} exists — reusing")

    ctrl_dsn = with_db(admin_dsn, NEW_DB)

    # 2) Schema + roles + grants inside sunstead_control.
    with connect(ctrl_dsn, autocommit=True) as conn, conn.cursor() as cur:
        # Strip line comments BEFORE splitting on ';' so a ';' inside a comment can't
        # split a statement; tolerate objects that already exist.
        raw = SCHEMA_PATH.read_text(encoding="utf-8")
        no_comments = "\n".join(re.sub(r"--.*$", "", ln) for ln in raw.splitlines())
        stmts = [s.strip() for s in no_comments.split(";") if s.strip()]
        new = 0
        for s in stmts:
            try:
                cur.execute(s)
                new += 1
            except (psycopg.errors.DuplicateTable, psycopg.errors.DuplicateObject):
                pass
        print(f"[schema] ran {len(stmts)} statements ({new} new)")

        for r in BROKERED:
            if not role_exists(cur, r):
                cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER").format(sql.Identifier(r)))
                print(f"[role] created {r}")
        if not role_exists(cur, "sunstead_app"):
            cur.execute(sql.SQL(
                "CREATE ROLE sunstead_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}"
            ).format(sql.Literal(app_pwd)))
            print("[role] created sunstead_app")
        else:
            cur.execute(sql.SQL("ALTER ROLE sunstead_app WITH PASSWORD {}").format(sql.Literal(app_pwd)))
            print("[role] sunstead_app exists — password ROTATED")

        for g in [
            "GRANT sunstead_readonly, sunstead_operator, sunstead_proposer TO sunstead_app",
            "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC",
            "GRANT USAGE ON SCHEMA public TO sunstead_readonly",
            "GRANT SELECT ON experiment, crossing, judgment, run TO sunstead_readonly",
            "GRANT sunstead_readonly TO sunstead_operator",
            "GRANT INSERT, UPDATE ON judgment, run TO sunstead_operator",
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sunstead_operator",
            "GRANT sunstead_readonly TO sunstead_proposer",
            "GRANT INSERT ON experiment, crossing TO sunstead_proposer",
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sunstead_proposer",
        ]:
            cur.execute(g)
        print("[grant] applied 10 grant/revoke statements")

    # 3) Verify least privilege as the app login.
    p = urlsplit(ctrl_dsn)
    app_dsn = urlunsplit((p.scheme, f"sunstead_app:{app_pwd}@{p.hostname}:{p.port}",
                          "/" + NEW_DB, "sslmode=require", ""))
    with connect(app_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)")
        is_super = cur.fetchone()[0]
        cur.execute("SET ROLE sunstead_proposer")
        cur.execute("SELECT count(*) FROM experiment")
        denied = False
        try:
            cur.execute("INSERT INTO judgment (crossing_id, judge, judge_kind, decision) "
                        "VALUES (NULL, 'x', 'human', 'approve')")
        except psycopg.errors.InsufficientPrivilege:
            denied = True
        cur.execute("RESET ROLE")
    print(f"[verify] rolsuper={is_super} (must be False); proposer DENIED judgment INSERT={denied} (must be True)")
    if is_super or not denied:
        print("[verify] FAILED — privilege boundary not as expected", file=sys.stderr)
        return 1

    # Secret out-of-band: write the DSN to a gitignored file; print only a masked line.
    out_path.write_text(app_dsn + "\n", encoding="utf-8")
    masked = app_dsn.replace(app_pwd, "****")
    print(f"\n[ok] app DSN written to {out_path} (gitignored). Masked: {masked}")
    print("     -> copy it into the APP_DSN secret, then delete the file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
