"""Logging client protocol and implementations.

Story B (GitHub issue #3) owns the production LogClient. This module defines
the contract protocol (so Stories A and C can type against it using fixtures)
AND the real PostgreSQL-backed implementation, `PgLogClient`.

The schema is frozen in `cleanroom/db/schema.sql` (experiment / crossing /
judgment). `PgLogClient` writes/reads those three tables over a psycopg3
connection, returning the same dict shape as the in-memory fixture so callers
(loop = Story A, boundary/dashboard = Story C) are backend-agnostic.
"""

from typing import Protocol

from cleanroom.types import PoreResult  # noqa: F401  (kept for contract/back-compat imports)


class LogClient(Protocol):
    """Protocol for writing and reading experiment/crossing/judgment records.

    Implementations must support both in-memory (for fixtures) and persistent
    (PostgreSQL, Story B) backends.
    """

    def write_experiment(
        self,
        task_id: str,
        model: str,
        drift_level: float,
        candidate: dict,
        baseline_p99: float | None,
        candidate_p99: float | None,
        cost_estimate: float | None,
        correctness_ok: bool | None,
        within_noise: bool | None,
        decision: str,
    ) -> int:
        """Write an experiment record. Returns the experiment id (bigint pk)."""
        ...

    def write_crossing(
        self,
        experiment_id: int,
        pore: str,
        risk_level: str,
        requires_human_judgment: bool,
        action: dict,
    ) -> int:
        """Write a crossing (pore evaluation) record. Returns the crossing id."""
        ...

    def write_judgment(
        self,
        crossing_id: int,
        judge: str,
        judge_kind: str,
        decision: str,
        rationale: str | None = None,
    ) -> None:
        """Write a judgment (human/rule/agent review) record."""
        ...

    def read_experiments(self, filter: dict | None = None) -> list[dict]:
        """Read experiment records, optionally filtered by column=value."""
        ...


# Column order for the experiment table, used to shape read_experiments() dicts.
_EXPERIMENT_COLUMNS = (
    "id",
    "task_id",
    "model",
    "drift_level",
    "candidate",
    "baseline_p99",
    "candidate_p99",
    "cost_estimate",
    "correctness_ok",
    "within_noise",
    "decision",
    "created_at",
)


class PgLogClient:
    """PostgreSQL-backed LogClient (psycopg3).

    Writes the frozen experiment/crossing/judgment tables. JSONB columns
    (`candidate`, `action`) are passed through psycopg's `Json` adapter so dicts
    serialize correctly.

    Connection ownership: by default the caller owns the connection lifecycle and
    `PgLogClient` does not close it. Each write commits — the log is an append-only
    audit trail; a crashed loop must never silently lose already-recorded
    experiments.

    Args:
        conn: An open psycopg3 connection. The same connection the loop hands to
            actions/benchmark can be reused here, or a dedicated one passed in.
    """

    _owns_conn = False

    def __init__(self, conn):
        self._conn = conn
        # Import here so the module imports cleanly in environments without psycopg
        # installed (e.g. Story A/C unit tests that only touch fixtures).
        from psycopg.types.json import Json

        self._Json = Json

    @classmethod
    def from_dsn(cls, dsn: str, **connect_kwargs) -> "PgLogClient":
        """Construct from a connection string (opens a new psycopg3 connection).

        The opened connection is owned by this client and closed in `close()`.
        """
        import psycopg

        conn = psycopg.connect(dsn, **connect_kwargs)
        client = cls(conn)
        client._owns_conn = True
        return client

    def write_experiment(
        self,
        task_id: str,
        model: str,
        drift_level: float,
        candidate: dict,
        baseline_p99: float | None,
        candidate_p99: float | None,
        cost_estimate: float | None,
        correctness_ok: bool | None,
        within_noise: bool | None,
        decision: str,
    ) -> int:
        sql = (
            "INSERT INTO experiment "
            "(task_id, model, drift_level, candidate, baseline_p99, candidate_p99, "
            " cost_estimate, correctness_ok, within_noise, decision) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"
        )
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    task_id,
                    model,
                    drift_level,
                    self._Json(candidate),
                    baseline_p99,
                    candidate_p99,
                    cost_estimate,
                    correctness_ok,
                    within_noise,
                    decision,
                ),
            )
            exp_id = cur.fetchone()[0]
        self._conn.commit()
        return exp_id

    def write_crossing(
        self,
        experiment_id: int,
        pore: str,
        risk_level: str,
        requires_human_judgment: bool,
        action: dict,
    ) -> int:
        sql = (
            "INSERT INTO crossing "
            "(experiment_id, pore, risk_level, requires_human_judgment, action) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        )
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    experiment_id,
                    pore,
                    risk_level,
                    requires_human_judgment,
                    self._Json(action),
                ),
            )
            crossing_id = cur.fetchone()[0]
        self._conn.commit()
        return crossing_id

    def write_judgment(
        self,
        crossing_id: int,
        judge: str,
        judge_kind: str,
        decision: str,
        rationale: str | None = None,
    ) -> None:
        sql = (
            "INSERT INTO judgment (crossing_id, judge, judge_kind, decision, rationale) "
            "VALUES (%s, %s, %s, %s, %s)"
        )
        with self._conn.cursor() as cur:
            cur.execute(sql, (crossing_id, judge, judge_kind, decision, rationale))
        self._conn.commit()

    def read_experiments(self, filter: dict | None = None) -> list[dict]:
        """Read experiment rows as dicts (same shape as the in-memory fixture).

        `filter` is an optional dict of column=value equality constraints. Column
        names are validated against the known schema to keep this injection-safe.
        """
        sql = f"SELECT {', '.join(_EXPERIMENT_COLUMNS)} FROM experiment"
        params: list = []
        if filter:
            unknown = set(filter) - set(_EXPERIMENT_COLUMNS)
            if unknown:
                raise ValueError(
                    f"read_experiments: unknown filter column(s) {sorted(unknown)}; "
                    f"valid columns are {list(_EXPERIMENT_COLUMNS)}"
                )
            clauses = [f"{col} = %s" for col in filter]
            sql += " WHERE " + " AND ".join(clauses)
            params = list(filter.values())
        sql += " ORDER BY id"

        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [dict(zip(_EXPERIMENT_COLUMNS, row)) for row in rows]

    def close(self) -> None:
        """Close the connection if this client opened it (via `from_dsn`)."""
        if self._owns_conn:
            self._conn.close()
