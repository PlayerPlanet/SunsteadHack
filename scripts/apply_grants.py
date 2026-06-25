#!/usr/bin/env python3
"""Apply an admin SQL file (grants) via psycopg — for hosts without the psql client.

Connects with the DSN in $ADMIN_DSN (the avnadmin / superuser login, the only role that
can GRANT on tables it owns) and runs each statement in the given .sql file, skipping
psql meta-commands (\\set ...) and comments. Prints any result rows (e.g. the trailing
verification SELECT). APPROVAL-GATED: this connects to the live shared Aiven service.

  ADMIN_DSN="postgres://avnadmin:...@...:.../sunstead_control?sslmode=require" \
    python scripts/apply_grants.py sql/grant_control_roles.sql
"""
from __future__ import annotations

import os
import sys

import psycopg


def _statements(sql_text: str):
    lines = []
    for line in sql_text.splitlines():
        s = line.strip()
        if s.startswith("\\") or s.startswith("--") or not s:
            continue
        # strip trailing inline comments (none contain ';' in our files)
        if "--" in line:
            line = line[: line.index("--")]
        lines.append(line)
    joined = "\n".join(lines)
    return [st.strip() for st in joined.split(";") if st.strip()]


def main() -> int:
    dsn = os.environ.get("ADMIN_DSN") or os.environ.get("CLEANROOM_PG_DSN")
    if not dsn:
        sys.exit("set ADMIN_DSN (avnadmin/superuser DSN) in the environment")
    path = sys.argv[1] if len(sys.argv) > 1 else "sql/grant_control_roles.sql"
    statements = _statements(open(path, encoding="utf-8").read())

    with psycopg.connect(dsn, connect_timeout=20) as conn:
        with conn.cursor() as cur:
            for st in statements:
                cur.execute(st)
                verb = st.split(None, 1)[0].upper()
                if cur.description:  # a SELECT — show it
                    print("  result:", cur.fetchall())
                else:
                    print(f"  ok: {verb} ...")
        conn.commit()
    print(f"applied {len(statements)} statements from {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
