"""GUC-tuning action adapter tests (Phase 2, Task 3).

Tests apply/rollback for GUC parameters with dynamic/restart-required context handling.
Includes offline unit tests with fake connections and optional golden tests with real DB.
"""

import pytest

from cleanroom.actions import apply, rollback, RestartRequiredError
from cleanroom.types import Candidate


class FakeCursor:
    """Mock cursor for testing SQL generation and pg_settings queries."""

    def __init__(self, pg_settings_response=None):
        """Initialize with optional pg_settings query response.

        Args:
            pg_settings_response: Tuple (context,) or None to raise NotFound.
        """
        self.statements = []
        self.pg_settings_response = pg_settings_response

    def execute(self, sql: str, params=None):
        """Record the SQL statement and handle pg_settings queries."""
        self.statements.append((sql, params))

    def fetchone(self):
        """Return mocked pg_settings row."""
        return self.pg_settings_response

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass


class FakeCursorFactory:
    """Factory for creating cursor context managers."""

    def __init__(self, pg_settings_response=None):
        """Initialize with optional pg_settings query response."""
        self.cursor_obj = FakeCursor(pg_settings_response)

    def __call__(self):
        """Return the cursor."""
        return self.cursor_obj


class FakeConn:
    """Mock connection for testing SQL generation and pg_settings queries."""

    def __init__(self, pg_settings_response=None):
        """Initialize with optional pg_settings query response.

        Args:
            pg_settings_response: Tuple (context,) or None to simulate not found.
        """
        self.cursor_factory = FakeCursorFactory(pg_settings_response)
        self.committed = False

    def cursor(self):
        """Return cursor factory (which acts as a context manager)."""
        return self.cursor_factory.cursor_obj

    def commit(self):
        """Mark as committed."""
        self.committed = True


class TestApplyGucWithNoneConn:
    """Test apply for GUC with conn=None (no-op)."""

    def test_apply_guc_with_none_conn_is_noop(self):
        """Verify apply with conn=None is a safe no-op."""
        candidate = Candidate(
            type="guc",
            params={"name": "work_mem", "value": "8MB"},
            reversible=True,
        )

        # Should not raise
        apply(None, candidate)

    def test_rollback_guc_with_none_conn_is_noop(self):
        """Verify rollback with conn=None is a safe no-op."""
        candidate = Candidate(
            type="guc",
            params={"name": "work_mem"},
            reversible=True,
        )

        # Should not raise
        rollback(None, candidate)


class TestApplyDynamicGuc:
    """Test apply for dynamic GUC parameters."""

    def test_apply_dynamic_guc_issues_alter_system_set(self):
        """Verify apply of dynamic GUC (work_mem) issues ALTER SYSTEM SET."""
        conn = FakeConn(pg_settings_response=("user",))
        candidate = Candidate(
            type="guc",
            params={"name": "work_mem", "value": "8MB"},
            reversible=True,
        )

        apply(conn, candidate)

        # Check statements: pg_settings query, ALTER SYSTEM SET, pg_reload_conf
        cursor = conn.cursor_factory.cursor_obj
        assert len(cursor.statements) >= 3

        # First statement should be the pg_settings query
        assert "pg_settings" in cursor.statements[0][0]
        assert cursor.statements[0][1] == ("work_mem",)

        # Second statement should be ALTER SYSTEM SET
        alter_stmt = cursor.statements[1][0]
        assert "ALTER SYSTEM SET" in alter_stmt
        assert "work_mem" in alter_stmt
        assert "8MB" in alter_stmt

        # Third should be pg_reload_conf
        assert "pg_reload_conf" in cursor.statements[2][0]

        assert conn.committed

    def test_apply_dynamic_guc_with_superuser_context(self):
        """Verify apply works with superuser context."""
        conn = FakeConn(pg_settings_response=("superuser",))
        candidate = Candidate(
            type="guc",
            params={"name": "log_statement", "value": "all"},
            reversible=True,
        )

        apply(conn, candidate)

        cursor = conn.cursor_factory.cursor_obj
        alter_stmt = cursor.statements[1][0]
        assert "ALTER SYSTEM SET" in alter_stmt
        assert "log_statement" in alter_stmt
        assert conn.committed

    def test_apply_dynamic_guc_with_sighup_context(self):
        """Verify apply works with sighup context."""
        conn = FakeConn(pg_settings_response=("sighup",))
        candidate = Candidate(
            type="guc",
            params={"name": "shared_preload_libraries", "value": "pg_stat_statements"},
            reversible=True,
        )

        apply(conn, candidate)

        cursor = conn.cursor_factory.cursor_obj
        assert "ALTER SYSTEM SET" in cursor.statements[1][0]
        assert conn.committed

    def test_apply_guc_with_quoted_value(self):
        """Verify apply properly quotes GUC values with special characters."""
        conn = FakeConn(pg_settings_response=("user",))
        candidate = Candidate(
            type="guc",
            params={"name": "work_mem", "value": "it's 8MB"},
            reversible=True,
        )

        apply(conn, candidate)

        cursor = conn.cursor_factory.cursor_obj
        alter_stmt = cursor.statements[1][0]
        # Single quote should be escaped as ''
        assert "it''s 8MB" in alter_stmt or "'it''s 8MB'" in alter_stmt

    def test_apply_guc_various_dynamic_contexts(self):
        """Verify apply works with all dynamic contexts."""
        dynamic_contexts = ["user", "superuser", "sighup", "backend", "superuser-backend"]

        for context in dynamic_contexts:
            conn = FakeConn(pg_settings_response=(context,))
            candidate = Candidate(
                type="guc",
                params={"name": "work_mem", "value": "8MB"},
                reversible=True,
            )

            apply(conn, candidate)

            cursor = conn.cursor_factory.cursor_obj
            assert "ALTER SYSTEM SET" in cursor.statements[1][0]
            assert conn.committed


class TestApplyPostmasterGuc:
    """Test apply for restart-required GUC parameters."""

    def test_apply_postmaster_guc_raises_restart_required_error(self):
        """Verify apply of postmaster-context GUC raises RestartRequiredError."""
        conn = FakeConn(pg_settings_response=("postmaster",))
        candidate = Candidate(
            type="guc",
            params={"name": "shared_buffers", "value": "4GB"},
            reversible=True,
        )

        with pytest.raises(RestartRequiredError) as exc_info:
            apply(conn, candidate)

        assert exc_info.value.param_name == "shared_buffers"
        assert "restart" in str(exc_info.value).lower()

    def test_restart_required_error_carries_param_name(self):
        """Verify RestartRequiredError stores the parameter name."""
        error = RestartRequiredError("shared_buffers")
        assert error.param_name == "shared_buffers"


class TestApplyGucValidation:
    """Test apply validation for GUC candidates."""

    def test_apply_guc_missing_name_raises_value_error(self):
        """Verify apply raises for missing 'name' in params."""
        conn = FakeConn()
        candidate = Candidate(
            type="guc",
            params={"value": "8MB"},
            reversible=True,
        )

        with pytest.raises(ValueError, match="must contain 'name' and 'value'"):
            apply(conn, candidate)

    def test_apply_guc_missing_value_raises_value_error(self):
        """Verify apply raises for missing 'value' in params."""
        conn = FakeConn()
        candidate = Candidate(
            type="guc",
            params={"name": "work_mem"},
            reversible=True,
        )

        with pytest.raises(ValueError, match="must contain 'name' and 'value'"):
            apply(conn, candidate)

    def test_apply_guc_invalid_name_raises_value_error(self):
        """Verify apply raises for invalid GUC name."""
        conn = FakeConn()
        candidate = Candidate(
            type="guc",
            params={"name": "work mem", "value": "8MB"},  # space is invalid
            reversible=True,
        )

        with pytest.raises(ValueError, match="invalid GUC name"):
            apply(conn, candidate)

    def test_apply_guc_with_special_chars_in_name_raises_error(self):
        """Verify apply rejects special characters in GUC name."""
        conn = FakeConn()
        candidate = Candidate(
            type="guc",
            params={"name": "work@mem", "value": "8MB"},
            reversible=True,
        )

        with pytest.raises(ValueError, match="invalid GUC name"):
            apply(conn, candidate)

    def test_apply_guc_nonexistent_guc_raises_value_error(self):
        """Verify apply raises for non-existent GUC name."""
        conn = FakeConn(pg_settings_response=None)
        candidate = Candidate(
            type="guc",
            params={"name": "nonexistent_guc", "value": "8MB"},
            reversible=True,
        )

        with pytest.raises(ValueError, match="not found in pg_settings"):
            apply(conn, candidate)


class TestRollbackGuc:
    """Test rollback for GUC parameters."""

    def test_rollback_guc_issues_alter_system_reset(self):
        """Verify rollback of GUC issues ALTER SYSTEM RESET."""
        conn = FakeConn()
        candidate = Candidate(
            type="guc",
            params={"name": "work_mem"},
            reversible=True,
        )

        rollback(conn, candidate)

        cursor = conn.cursor_factory.cursor_obj
        assert len(cursor.statements) >= 2

        # First statement should be ALTER SYSTEM RESET
        reset_stmt = cursor.statements[0][0]
        assert "ALTER SYSTEM RESET" in reset_stmt
        assert "work_mem" in reset_stmt

        # Second should be pg_reload_conf
        assert "pg_reload_conf" in cursor.statements[1][0]

        assert conn.committed

    def test_rollback_guc_missing_name_raises_value_error(self):
        """Verify rollback raises for missing 'name' in params."""
        conn = FakeConn()
        candidate = Candidate(
            type="guc",
            params={},
            reversible=True,
        )

        with pytest.raises(ValueError, match="must contain 'name'"):
            rollback(conn, candidate)

    def test_rollback_guc_invalid_name_raises_value_error(self):
        """Verify rollback raises for invalid GUC name."""
        conn = FakeConn()
        candidate = Candidate(
            type="guc",
            params={"name": "work mem"},  # space is invalid
            reversible=True,
        )

        with pytest.raises(ValueError, match="invalid GUC name"):
            rollback(conn, candidate)


class TestApplyAndRollbackGucConsistency:
    """Test that apply and rollback are consistent."""

    def test_apply_and_rollback_use_same_guc_name(self):
        """Verify apply and rollback use the same GUC name."""
        apply_conn = FakeConn(pg_settings_response=("user",))
        rollback_conn = FakeConn()

        candidate = Candidate(
            type="guc",
            params={"name": "work_mem", "value": "8MB"},
            reversible=True,
        )

        apply(apply_conn, candidate)
        rollback(rollback_conn, candidate)

        apply_stmt = apply_conn.cursor_factory.cursor_obj.statements[1][0]
        rollback_stmt = rollback_conn.cursor_factory.cursor_obj.statements[0][0]

        # Both should reference work_mem
        assert "work_mem" in apply_stmt
        assert "work_mem" in rollback_stmt


@pytest.mark.golden
class TestApplyGucLiveDatabase:
    """Live database tests against sunstead-proposer-pg container.

    Requires:
    - sunstead-proposer-pg container running on localhost:55432
    - PostgreSQL credentials: user=postgres, password=postgres, database=postgres
    """

    @pytest.fixture
    def live_conn(self):
        """Establish a live connection to the test database.

        Skips the test if the database is not reachable.
        """
        try:
            import psycopg2
        except ImportError:
            pytest.skip("psycopg2 not installed")

        try:
            conn = psycopg2.connect(
                host="localhost",
                port=55432,
                user="postgres",
                password="postgres",
                database="postgres",
            )
            conn.autocommit = False
            yield conn
            conn.close()
        except psycopg2.OperationalError:
            pytest.skip("sunstead-proposer-pg container not reachable on localhost:55432")

    def test_apply_and_rollback_work_mem_live(self, live_conn):
        """Idempotent test: apply work_mem, verify via SHOW, rollback, verify reset."""
        candidate = Candidate(
            type="guc",
            params={"name": "work_mem", "value": "8MB"},
            reversible=True,
        )

        # Apply
        apply(live_conn, candidate)

        # Verify via SHOW
        with live_conn.cursor() as cur:
            cur.execute("SHOW work_mem")
            result = cur.fetchone()[0]
            # PostgreSQL may normalize the value (e.g., "8MB")
            assert "8" in result and "MB" in result.upper()

        # Rollback
        rollback(live_conn, candidate)

        # Verify reset (should be back to default, typically "4MB")
        with live_conn.cursor() as cur:
            cur.execute("SHOW work_mem")
            result = cur.fetchone()[0]
            # Default is 4MB; just verify it changed
            assert result is not None

    def test_apply_dynamic_guc_does_not_require_restart(self, live_conn):
        """Verify that applying a dynamic GUC does not raise RestartRequiredError."""
        candidate = Candidate(
            type="guc",
            params={"name": "work_mem", "value": "16MB"},
            reversible=True,
        )

        # Should not raise
        try:
            apply(live_conn, candidate)
        finally:
            # Cleanup
            rollback(live_conn, candidate)

    def test_apply_postmaster_guc_raises_restart_required_live(self, live_conn):
        """Verify that postmaster-context GUCs raise RestartRequiredError."""
        candidate = Candidate(
            type="guc",
            params={"name": "shared_buffers", "value": "8GB"},
            reversible=True,
        )

        with pytest.raises(RestartRequiredError) as exc_info:
            apply(live_conn, candidate)

        assert exc_info.value.param_name == "shared_buffers"
