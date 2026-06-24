"""PostgreSQL-backed run store for dispatcher (Story D, Phase 0).

Persists RunStatus records to a new `run` table in the Aiven knowledge base.
Mirrors PgLogClient's conventions: caller owns conn, from_dsn classmethod,
lazy psycopg import, commit on writes.

CONCURRENCY: The dispatcher updates run state from a daemon thread (executor.py).
psycopg3 connections are not safe for concurrent use, so all operations are
guarded by a threading.Lock. This ensures only one thread accesses the cursor
or commits at a time.
"""

import threading

from cleanroom.control.dispatcher.state import RunStatus


class PgRunStore:
    """PostgreSQL-backed run store.

    Stores RunStatus records to the `run` table. Each operation commits
    immediately to keep the run log durable (crashes must not lose
    already-recorded state changes).

    Connection ownership: by default the caller owns the connection lifecycle
    and PgRunStore does not close it. Use from_dsn() to have the store open
    and own a connection.

    Args:
        conn: An open psycopg3 connection. The same connection the dispatcher
            or tests hand to benchmark/actions can be reused here.
    """

    _owns_conn = False

    def __init__(self, conn):
        """Initialize the store with a connection.

        Args:
            conn: An open psycopg3 connection.
        """
        self._conn = conn
        self._lock = threading.Lock()

    @classmethod
    def from_dsn(cls, dsn: str, **connect_kwargs) -> "PgRunStore":
        """Construct from a connection string (opens a new psycopg3 connection).

        The opened connection is owned by this store and closed in close().

        Args:
            dsn: PostgreSQL connection string.
            **connect_kwargs: Additional kwargs for psycopg.connect().

        Returns:
            A new PgRunStore instance.
        """
        import psycopg

        conn = psycopg.connect(dsn, **connect_kwargs)
        store = cls(conn)
        store._owns_conn = True
        return store

    def get(self, run_id: str) -> RunStatus | None:
        """Retrieve a run by ID.

        Args:
            run_id: Run identifier.

        Returns:
            RunStatus if found, None otherwise.
        """
        sql = (
            "SELECT run_id, task_id, model, state, iterations_done, best_p99, "
            "       started_at, ended_at, error_msg "
            "FROM run WHERE run_id = %s"
        )
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(sql, (run_id,))
                row = cur.fetchone()

        if row is None:
            return None

        return RunStatus(
            run_id=row[0],
            task_id=row[1],
            model=row[2],
            state=row[3],
            iterations_done=row[4],
            best_p99=row[5],
            started_at=row[6],
            ended_at=row[7],
            error_msg=row[8],
        )

    def set(self, run_id: str, status: RunStatus) -> None:
        """Store or overwrite a run.

        Uses INSERT ... ON CONFLICT (run_id) DO UPDATE to ensure idempotency:
        multiple calls with the same run_id will succeed and update the record.

        Args:
            run_id: Run identifier (must match status.run_id).
            status: RunStatus object to store.
        """
        sql = (
            "INSERT INTO run "
            "(run_id, task_id, model, state, iterations_done, best_p99, "
            " started_at, ended_at, error_msg) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (run_id) DO UPDATE SET "
            "  task_id = EXCLUDED.task_id, "
            "  model = EXCLUDED.model, "
            "  state = EXCLUDED.state, "
            "  iterations_done = EXCLUDED.iterations_done, "
            "  best_p99 = EXCLUDED.best_p99, "
            "  started_at = EXCLUDED.started_at, "
            "  ended_at = EXCLUDED.ended_at, "
            "  error_msg = EXCLUDED.error_msg"
        )
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        status.run_id,
                        status.task_id,
                        status.model,
                        status.state,
                        status.iterations_done,
                        status.best_p99,
                        status.started_at,
                        status.ended_at,
                        status.error_msg,
                    ),
                )
            self._conn.commit()

    def list(self, filter: dict | None = None) -> list[RunStatus]:
        """List runs, optionally filtered by field=value.

        Args:
            filter: Optional dict of field=value constraints. Only valid field
                names (from RunStatus) are allowed; unknown keys raise ValueError.

        Returns:
            List of matching RunStatus objects.
        """
        # Validate filter keys against known RunStatus fields
        valid_fields = {
            "run_id",
            "task_id",
            "model",
            "state",
            "iterations_done",
            "best_p99",
            "started_at",
            "ended_at",
            "error_msg",
        }
        if filter:
            unknown = set(filter) - valid_fields
            if unknown:
                raise ValueError(
                    f"list: unknown filter field(s) {sorted(unknown)}; "
                    f"valid fields are {sorted(valid_fields)}"
                )

        sql = (
            "SELECT run_id, task_id, model, state, iterations_done, best_p99, "
            "       started_at, ended_at, error_msg "
            "FROM run"
        )
        params: list = []
        if filter:
            clauses = [f"{col} = %s" for col in filter]
            sql += " WHERE " + " AND ".join(clauses)
            params = list(filter.values())
        sql += " ORDER BY run_id"

        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        return [
            RunStatus(
                run_id=row[0],
                task_id=row[1],
                model=row[2],
                state=row[3],
                iterations_done=row[4],
                best_p99=row[5],
                started_at=row[6],
                ended_at=row[7],
                error_msg=row[8],
            )
            for row in rows
        ]

    def update(self, run_id: str, **fields) -> RunStatus | None:
        """Update specific fields of a run.

        Only allows updates to known RunStatus fields; unknown field names
        raise ValueError. Returns the updated RunStatus or None if the run
        doesn't exist.

        Args:
            run_id: Run identifier.
            **fields: Fields to update (e.g., state='done', iterations_done=5).

        Returns:
            Updated RunStatus, or None if not found.
        """
        # Validate that only known fields are being updated
        valid_fields = {
            "task_id",
            "model",
            "state",
            "iterations_done",
            "best_p99",
            "started_at",
            "ended_at",
            "error_msg",
        }
        unknown = set(fields) - valid_fields
        if unknown:
            raise ValueError(
                f"update: unknown field(s) {sorted(unknown)}; "
                f"valid fields are {sorted(valid_fields)}"
            )

        if not fields:
            # No fields to update; just return the current status
            return self.get(run_id)

        # Build the dynamic UPDATE clause
        clauses = [f"{col} = %s" for col in fields]
        sql = f"UPDATE run SET {', '.join(clauses)} WHERE run_id = %s RETURNING run_id, task_id, model, state, iterations_done, best_p99, started_at, ended_at, error_msg"
        params = list(fields.values()) + [run_id]

        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
            self._conn.commit()

        if row is None:
            return None

        return RunStatus(
            run_id=row[0],
            task_id=row[1],
            model=row[2],
            state=row[3],
            iterations_done=row[4],
            best_p99=row[5],
            started_at=row[6],
            ended_at=row[7],
            error_msg=row[8],
        )

    def close(self) -> None:
        """Close the connection if this store opened it (via from_dsn())."""
        if self._owns_conn:
            with self._lock:
                self._conn.close()
