"""Unit tests for Postgres role-brokering (no live DB — a fake cursor records SQL)."""

import pytest

from cleanroom.control.server.roles import (
    ROLE_OPERATOR,
    RoleError,
    apply_role,
    assert_not_superuser,
    reset_role,
    role_scope,
    validate_role,
)


class FakeCursor:
    def __init__(self, fetch_row=None):
        self.executed: list[str] = []
        self._fetch_row = fetch_row

    def execute(self, sql, params=None):
        self.executed.append(sql)

    def fetchone(self):
        return self._fetch_row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, fetch_row=None):
        self.cursors: list[FakeCursor] = []
        self._fetch_row = fetch_row

    def cursor(self):
        cur = FakeCursor(self._fetch_row)
        self.cursors.append(cur)
        return cur


def test_validate_role_allows_provisioned():
    assert validate_role(ROLE_OPERATOR) == ROLE_OPERATOR


def test_validate_role_rejects_unprovisioned():
    with pytest.raises(RoleError):
        validate_role("postgres")
    with pytest.raises(RoleError):
        validate_role("avnadmin")


def test_apply_role_emits_quoted_set_role():
    cur = FakeCursor()
    apply_role(cur, ROLE_OPERATOR)
    assert cur.executed == [f'SET ROLE "{ROLE_OPERATOR}"']


def test_apply_role_rejects_bad_role_without_executing():
    cur = FakeCursor()
    with pytest.raises(RoleError):
        apply_role(cur, "'; DROP TABLE judgment; --")
    assert cur.executed == []  # nothing reached the DB


def test_reset_role():
    cur = FakeCursor()
    reset_role(cur)
    assert cur.executed == ["RESET ROLE"]


def test_role_scope_applies_then_resets():
    conn = FakeConn()
    with role_scope(conn, ROLE_OPERATOR):
        pass
    emitted = [sql for cur in conn.cursors for sql in cur.executed]
    assert emitted == [f'SET ROLE "{ROLE_OPERATOR}"', "RESET ROLE"]


def test_role_scope_validates_before_touching_db():
    conn = FakeConn()
    with pytest.raises(RoleError):
        with role_scope(conn, "superuser"):
            pass
    assert all(cur.executed == [] for cur in conn.cursors)


def test_assert_not_superuser_raises_for_superuser():
    conn = FakeConn(fetch_row=(True,))
    with pytest.raises(RoleError):
        assert_not_superuser(conn)


def test_assert_not_superuser_passes_for_normal_login():
    conn = FakeConn(fetch_row=(False,))
    assert_not_superuser(conn)  # no raise


def test_assert_not_superuser_passes_when_role_row_missing():
    conn = FakeConn(fetch_row=None)
    assert_not_superuser(conn)  # treat unknown as non-super; fail-open here is safe
