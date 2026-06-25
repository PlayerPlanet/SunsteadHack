"""Tests for the Secrets Manager DSN resolution in wiring (AgentCore runtime path).

boto3 isn't a test dependency, so a fake module is injected. These verify the
precedence (explicit DSN > Secrets Manager), the one-shot caching, and that a
Secrets-Manager DSN marks migrations as external (the serving login lacks CREATE).
"""

import sys
import types

import pytest

from cleanroom.control.server import wiring

_SECRET_DSN = "postgres://sunstead_app:pw@h:11244/sunstead_control?sslmode=require"


def _install_fake_boto3(monkeypatch, dsn, calls):
    fake = types.ModuleType("boto3")

    class _SM:
        def get_secret_value(self, SecretId):
            calls.append(SecretId)
            return {"SecretString": dsn}

    def client(name, **kw):
        assert name == "secretsmanager"
        return _SM()

    fake.client = client
    monkeypatch.setitem(sys.modules, "boto3", fake)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for v in ("CLEANROOM_PG_APP_DSN", "CLEANROOM_PG_DSN", "CLEANROOM_PG_SECRET_ID",
              "CLEANROOM_PG_SECRET_ARN", "AWS_REGION"):
        monkeypatch.delenv(v, raising=False)
    wiring.reset_caches()
    yield
    wiring.reset_caches()


def test_secret_fetched_when_only_secret_id_set(monkeypatch):
    calls = []
    _install_fake_boto3(monkeypatch, _SECRET_DSN, calls)
    monkeypatch.setenv("CLEANROOM_PG_SECRET_ID", "sunstead/app-dsn")
    assert wiring.data_dsn() == _SECRET_DSN
    assert calls == ["sunstead/app-dsn"]


def test_secret_dsn_cached_one_fetch(monkeypatch):
    calls = []
    _install_fake_boto3(monkeypatch, _SECRET_DSN, calls)
    monkeypatch.setenv("CLEANROOM_PG_SECRET_ARN", "arn:aws:secretsmanager:...:secret:x")
    wiring.data_dsn()
    wiring.data_dsn()
    assert len(calls) == 1  # cached after the first hit


def test_explicit_dsn_takes_precedence_no_fetch(monkeypatch):
    calls = []
    _install_fake_boto3(monkeypatch, _SECRET_DSN, calls)
    monkeypatch.setenv("CLEANROOM_PG_SECRET_ID", "x")
    monkeypatch.setenv("CLEANROOM_PG_APP_DSN", "postgres://app-login")
    assert wiring.data_dsn() == "postgres://app-login"
    assert calls == []  # secret never touched


def test_external_migrations_true_with_secret(monkeypatch):
    monkeypatch.setenv("CLEANROOM_PG_SECRET_ID", "x")
    assert wiring._external_migrations() is True


def test_secret_value_is_stripped(monkeypatch):
    calls = []
    _install_fake_boto3(monkeypatch, _SECRET_DSN + "\n", calls)  # trailing newline from a file
    monkeypatch.setenv("CLEANROOM_PG_SECRET_ID", "x")
    assert wiring.data_dsn() == _SECRET_DSN


def test_no_dsn_anywhere_is_none(monkeypatch):
    assert wiring.data_dsn() is None
