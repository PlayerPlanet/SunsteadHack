"""Database schema and connection utilities.

Story B (GitHub issue #3) owns schema initialization and connection.

Thin helpers so the loop's integration point #1 (wiring the harness to the real
Aiven service) is a one-liner:

    from cleanroom.db import connect, init_schema
    conn = connect()            # reads CLEANROOM_PG_DSN
    init_schema(conn)           # idempotently applies schema.sql

Connection facts for `sunstead-pg-bench` (docs/aiven_mcp_notes.md):
  * TLS is required; Aiven uses a self-signed project CA. Pass `sslmode=require`
    (or verify against the CA) in the DSN — never disable verification.
  * Pull a live DSN with the `aiven_service_connection_info` MCP tool at wire-up
    time and put it in CLEANROOM_PG_DSN (a gitignored .env), not in source.
"""

import os
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

#: Tables defined by the frozen schema, in dependency order.
_SCHEMA_TABLES = ("experiment", "crossing", "judgment")


def connect(dsn: str | None = None, **connect_kwargs):
    """Open a psycopg3 connection.

    Args:
        dsn: Connection string. Falls back to the CLEANROOM_PG_DSN env var.
        **connect_kwargs: Passed through to psycopg.connect (e.g. autocommit=True).

    Returns:
        An open psycopg3 connection (caller owns its lifecycle).

    Raises:
        RuntimeError: If no DSN is provided and CLEANROOM_PG_DSN is unset.
    """
    import psycopg

    dsn = dsn or os.environ.get("CLEANROOM_PG_DSN")
    if not dsn:
        raise RuntimeError(
            "connect: no DSN given and CLEANROOM_PG_DSN is unset. Fetch a live DSN via "
            "the aiven_service_connection_info MCP tool and export CLEANROOM_PG_DSN."
        )
    return psycopg.connect(dsn, **connect_kwargs)


def init_schema(conn) -> None:
    """Apply `schema.sql` to the connection (idempotent).

    schema.sql uses bare `create table`; to stay safely re-runnable we skip
    application when all frozen tables already exist, rather than rewriting the
    committed DDL.
    """
    if _tables_exist(conn):
        return
    ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def _tables_exist(conn) -> bool:
    """True iff every frozen schema table is already present in the public schema."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY(%s)",
            (list(_SCHEMA_TABLES),),
        )
        count = cur.fetchone()[0]
    return count == len(_SCHEMA_TABLES)
