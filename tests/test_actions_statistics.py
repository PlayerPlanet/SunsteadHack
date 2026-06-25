"""Extended-statistics action tests (the JOB-complex 'missing action').

Offline unit tests with a fake connection: assert the SQL apply/rollback emit for a
`statistics` candidate (CREATE STATISTICS + ANALYZE / DROP STATISTICS), the >=2-column
and kinds validation, and the conn=None no-op.
"""

import pytest

from cleanroom.actions import apply, rollback, _make_stats_name
from cleanroom.types import Candidate


class _Cur:
    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(sql)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self):
        self._cur = _Cur()
        self.committed = False

    def cursor(self):
        return self._cur

    def commit(self):
        self.committed = True


def _stats(cols=("production_year", "kind_id"), kinds=None):
    params = {"table": "title", "columns": list(cols)}
    if kinds is not None:
        params["kinds"] = kinds
    return Candidate(type="statistics", params=params, reversible=True)


def test_none_conn_is_noop():
    apply(None, _stats())
    rollback(None, _stats())  # must not raise


def test_apply_emits_create_statistics_then_analyze():
    conn = _Conn()
    apply(conn, _stats())
    sql = conn._cur.statements
    name = _make_stats_name("title", ["production_year", "kind_id"])
    assert any(s.startswith(f'CREATE STATISTICS IF NOT EXISTS "{name}"') for s in sql)
    assert any('ON "production_year", "kind_id" FROM "title"' in s for s in sql)
    assert any(s == 'ANALYZE "title"' for s in sql)  # extended stats need ANALYZE
    assert conn.committed


def test_apply_with_kinds_clause():
    conn = _Conn()
    apply(conn, _stats(kinds=["ndistinct", "dependencies"]))
    create = next(s for s in conn._cur.statements if s.startswith("CREATE STATISTICS"))
    assert "(ndistinct, dependencies)" in create


def test_apply_requires_two_columns():
    with pytest.raises(ValueError, match=">=2"):
        apply(_Conn(), _stats(cols=("production_year",)))


def test_apply_rejects_unknown_kinds():
    with pytest.raises(ValueError, match="invalid statistics kinds"):
        apply(_Conn(), _stats(kinds=["bogus"]))


def test_rollback_drops_statistics():
    conn = _Conn()
    rollback(conn, _stats())
    name = _make_stats_name("title", ["production_year", "kind_id"])
    assert conn._cur.statements == [f'DROP STATISTICS IF EXISTS "{name}"']
    assert conn.committed


def test_stats_name_is_deterministic_and_prefixed():
    a = _make_stats_name("title", ["production_year", "kind_id"])
    b = _make_stats_name("title", ["production_year", "kind_id"])
    assert a == b and a.startswith("stx_title_")
