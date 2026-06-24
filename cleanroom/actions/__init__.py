"""Candidate application and rollback.

Story A (GitHub issue #2) owns the apply/rollback implementation.

Task 1 = index discovery. NOTE: hypopg is NOT available on our Aiven plan
(verified 2026-06-24, service sunstead-pg-bench) — so apply/rollback use a real
CREATE INDEX / DROP INDEX on a small dataset (reversible, sub-second build) rather
than a hypothetical-index proxy. See GitHub issue #2 (Gate-1 update).

Phase 2, Task 3: GUC-tuning action adapter handles dynamic and restart-required GUC parameters.
"""

import hashlib
import re

from cleanroom.types import Candidate


class RestartRequiredError(Exception):
    """Raised when attempting to apply a postmaster-context GUC without restart.

    Attributes:
        param_name: The name of the GUC parameter requiring restart.
    """

    def __init__(self, param_name: str):
        """Initialize RestartRequiredError.

        Args:
            param_name: The name of the GUC parameter.
        """
        self.param_name = param_name
        super().__init__(
            f"GUC parameter '{param_name}' requires server restart (context='postmaster'); "
            "apply live if dynamic, flag restart-required"
        )


def _make_index_name(table: str, columns: list[str]) -> str:
    """Derive a deterministic index name from table and column names.

    Args:
        table: The table name.
        columns: List of column names to index.

    Returns:
        A deterministic index name (e.g., 'idx_table_col1_col2_<hash>').
    """
    # Create a short hash of the full spec to ensure uniqueness
    spec = f"{table}_{','.join(columns)}"
    hash_suffix = hashlib.md5(spec.encode()).hexdigest()[:8]
    col_str = "_".join(columns)
    return f"idx_{table}_{col_str}_{hash_suffix}"


def _validate_guc_name(name: str) -> None:
    """Validate that a GUC name is safe for use in ALTER SYSTEM.

    Args:
        name: The GUC parameter name to validate.

    Raises:
        ValueError: If the name contains invalid characters.
    """
    if not re.match(r"^[A-Za-z0-9_.]+$", name):
        raise ValueError(
            f"apply: invalid GUC name '{name}'; must match ^[A-Za-z0-9_.]+$"
        )


def _quote_guc_value(value) -> str:
    """Quote a GUC value for use in ALTER SYSTEM.

    Converts the value to a string and escapes single quotes.

    Args:
        value: The value to quote.

    Returns:
        A properly quoted string suitable for ALTER SYSTEM SET.
    """
    str_val = str(value)
    # Escape single quotes by doubling them
    escaped = str_val.replace("'", "''")
    return f"'{escaped}'"


def apply(conn, candidate: Candidate) -> None:
    """Apply the candidate to the database.

    Supports candidate.type in {"index", "guc"}.

    If conn is None (fixture/test mode), this is a no-op.
    If conn is real:
      - For "index": executes CREATE INDEX IF NOT EXISTS on the specified table+columns.
      - For "guc": applies a GUC parameter; raises RestartRequiredError if postmaster-context.

    Args:
        conn: A database connection object (or None for Phase-0 fixture mode).
        candidate: The candidate to apply.

    Raises:
        ValueError: If candidate.type is not "index" or "guc", or if params are invalid.
        RestartRequiredError: If applying a postmaster-context GUC without restart.
    """
    if conn is None:
        # Phase-0 fixture mode: no-op
        return

    if candidate.type == "index":
        # Extract table and columns from params
        table = candidate.params.get("table")
        columns = candidate.params.get("columns")

        if not table or not columns:
            raise ValueError(
                f"apply: candidate.params must contain 'table' and 'columns', "
                f"got {candidate.params}"
            )

        index_name = _make_index_name(table, columns)
        col_str = ", ".join(f'"{c}"' for c in columns)

        sql = f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table}" ({col_str})'

        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    elif candidate.type == "guc":
        # Extract name and value from params
        name = candidate.params.get("name")
        value = candidate.params.get("value")

        if not name or value is None:
            raise ValueError(
                f"apply: GUC candidate.params must contain 'name' and 'value', "
                f"got {candidate.params}"
            )

        # Validate GUC name
        _validate_guc_name(name)

        # Check if the GUC is dynamic or requires restart
        with conn.cursor() as cur:
            cur.execute(
                "SELECT context FROM pg_settings WHERE name = %s",
                (name,)
            )
            row = cur.fetchone()

        if row is None:
            raise ValueError(f"apply: GUC parameter '{name}' not found in pg_settings")

        context = row[0]

        # If postmaster-context, raise RestartRequiredError
        if context == "postmaster":
            raise RestartRequiredError(name)

        # If dynamic, apply the setting
        if context in {"user", "superuser", "sighup", "backend", "superuser-backend"}:
            quoted_value = _quote_guc_value(value)
            sql = f"ALTER SYSTEM SET {name} = {quoted_value}"

            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("SELECT pg_reload_conf()")
            conn.commit()
        else:
            # Unexpected context value
            raise ValueError(
                f"apply: unexpected GUC context '{context}' for '{name}'; "
                "expected 'postmaster' or one of {user,superuser,sighup,backend,superuser-backend}"
            )

    else:
        raise ValueError(
            f"apply: unsupported candidate type '{candidate.type}' "
            "(supported types: 'index', 'guc')"
        )


def rollback(conn, candidate: Candidate) -> None:
    """Rollback the candidate from the database.

    Supports candidate.type in {"index", "guc"}.

    If conn is None (fixture/test mode), this is a no-op.
    If conn is real:
      - For "index": executes DROP INDEX IF EXISTS on the index derived from candidate.
      - For "guc": executes ALTER SYSTEM RESET to restore the default/previous configured value.

    Args:
        conn: A database connection object (or None for Phase-0 fixture mode).
        candidate: The candidate to rollback.

    Raises:
        ValueError: If candidate.type is not "index" or "guc", or if params are invalid.
    """
    if conn is None:
        # Phase-0 fixture mode: no-op
        return

    if candidate.type == "index":
        # Extract table and columns from params
        table = candidate.params.get("table")
        columns = candidate.params.get("columns")

        if not table or not columns:
            raise ValueError(
                f"rollback: candidate.params must contain 'table' and 'columns', "
                f"got {candidate.params}"
            )

        index_name = _make_index_name(table, columns)

        sql = f'DROP INDEX IF EXISTS "{index_name}"'

        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    elif candidate.type == "guc":
        # Extract name from params
        name = candidate.params.get("name")

        if not name:
            raise ValueError(
                f"rollback: GUC candidate.params must contain 'name', "
                f"got {candidate.params}"
            )

        # Validate GUC name
        _validate_guc_name(name)

        # Execute ALTER SYSTEM RESET to restore default/previous value
        sql = f"ALTER SYSTEM RESET {name}"

        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute("SELECT pg_reload_conf()")
        conn.commit()

    else:
        raise ValueError(
            f"rollback: unsupported candidate type '{candidate.type}' "
            "(supported types: 'index', 'guc')"
        )
