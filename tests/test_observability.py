"""Tests for structured logging, request context, Sentry, and DB backup."""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from bulletin_maker.web import backup, db, observability, security
from bulletin_maker.web.artifacts import LocalArtifactStore, StoredObject
from bulletin_maker.web.server import create_app

TEST_DATABASE_URL = os.environ.get(
    "BULLETIN_TEST_DATABASE_URL", "postgresql://localhost/bulletin_maker_test")

_TRUNCATE = (
    "TRUNCATE churches, users, past_runs, sessions, auth_tokens, jobs,"
    " artifacts, sns_cache, audit_log RESTART IDENTITY CASCADE"
)

REG = {
    "church_name": "St. Test Lutheran",
    "email": "admin@sttest.org",
    "password": "correct-horse-battery",
    "display_name": "Pat Admin",
}


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    db.reset_for_tests()
    with db.connect() as conn:
        conn.execute(_TRUNCATE)
        conn.execute(
            "INSERT INTO plans (plan) VALUES ('free') ON CONFLICT DO NOTHING")
    monkeypatch.setattr(security, "KEYFILE", tmp_path / "secret.key")
    monkeypatch.delenv("BULLETIN_SECRET_KEY", raising=False)
    monkeypatch.delenv("BULLETIN_HOSTED", raising=False)
    monkeypatch.delenv("BULLETIN_LOG_JSON", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setenv("ARTIFACT_STORE", "local")
    monkeypatch.setenv("BULLETIN_ARTIFACT_DIR", str(tmp_path / "artifacts"))


@pytest.fixture()
def client():
    with TestClient(create_app()) as tc:
        yield tc


def _mock_sns(monkeypatch):
    instance = MagicMock()
    monkeypatch.setattr(
        "bulletin_maker.web.server.SundaysClient", lambda: instance)
    return instance


def _register_and_link(client, monkeypatch):
    _mock_sns(monkeypatch)
    assert client.post("/api/register", json=REG).status_code == 200
    resp = client.put("/api/church/sns-link",
                      json={"username": "church@sns.org", "password": "snspw"})
    assert resp.status_code == 200


# ── Request id header ─────────────────────────────────────────────────

class TestRequestId:

    def test_header_present(self, client):
        resp = client.get("/api/instance")
        assert resp.headers.get("X-Request-Id")
        assert len(resp.headers["X-Request-Id"]) == observability.REQUEST_ID_LENGTH

    def test_header_unique_per_request(self, client):
        first = client.get("/api/instance").headers["X-Request-Id"]
        second = client.get("/api/instance").headers["X-Request-Id"]
        assert first != second


# ── JSON logging ──────────────────────────────────────────────────────

def _capture_json(logger_name: str = "bulletin_maker.test"):
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.addFilter(observability.ContextFilter())
    handler.setFormatter(observability.JsonLogFormatter())
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    return logger, handler, buffer


class TestJsonLogging:

    def test_emits_parseable_json_with_request_id(self):
        logger, handler, buffer = _capture_json()
        observability.bind_context(request_id="reqid1234567")
        try:
            logger.warning("something happened")
        finally:
            logger.removeHandler(handler)
        record = json.loads(buffer.getvalue().strip())
        assert record["message"] == "something happened"
        assert record["request_id"] == "reqid1234567"
        assert record["level"] == "WARNING"
        assert "ts" in record and "logger" in record

    def test_null_fields_omitted(self):
        logger, handler, buffer = _capture_json("bulletin_maker.test.null")
        observability.bind_context(request_id="onlyrequestid")
        try:
            logger.warning("no church")
        finally:
            logger.removeHandler(handler)
        record = json.loads(buffer.getvalue().strip())
        assert "church_id" not in record
        assert "user_id" not in record
        assert "job_id" not in record

    def test_setup_logging_selects_json(self, monkeypatch):
        monkeypatch.setenv("BULLETIN_LOG_JSON", "1")
        observability.setup_logging()
        our = [h for h in logging.getLogger().handlers
               if getattr(h, "_bulletin_observability", False)]
        assert our and isinstance(our[0].formatter, observability.JsonLogFormatter)
        monkeypatch.delenv("BULLETIN_LOG_JSON")
        observability.setup_logging()


# ── Context binding through a request ─────────────────────────────────

class TestContextBinding:

    def test_church_id_bound_after_login(self, client, monkeypatch):
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Capture()
        handler.addFilter(observability.ContextFilter())
        logger = logging.getLogger("bulletin_maker")
        logger.addHandler(handler)
        try:
            _register_and_link(client, monkeypatch)
        finally:
            logger.removeHandler(handler)

        linked = [r for r in records if "linked" in r.getMessage()]
        assert linked, "expected the S&S link warning to be logged"
        assert linked[0].church_id == 1


# ── Sentry dormant ────────────────────────────────────────────────────

class TestSentry:

    def test_noop_without_dsn(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        sys.modules.pop("sentry_sdk", None)
        observability.init_sentry()
        assert "sentry_sdk" not in sys.modules


# ── Backup prune / list logic ─────────────────────────────────────────

def _fabricate_backups(store, timestamps):
    for stamp in timestamps:
        store.put(f"backups/{stamp}.dump", f"dump-{stamp}".encode())


class TestBackupPrune:

    def test_keys_to_prune_keeps_newest(self):
        keys = [
            "backups/20240101T000000Z.dump",
            "backups/20240102T000000Z.dump",
            "backups/20240103T000000Z.dump",
            "backups/20240104T000000Z.dump",
        ]
        doomed = backup.keys_to_prune(keys, keep=2)
        assert doomed == [
            "backups/20240101T000000Z.dump",
            "backups/20240102T000000Z.dump",
        ]

    def test_keys_to_prune_under_limit(self):
        keys = ["backups/20240101T000000Z.dump"]
        assert backup.keys_to_prune(keys, keep=14) == []

    def test_prune_deletes_oldest_against_store(self, tmp_path):
        store = LocalArtifactStore(tmp_path)
        stamps = ["20240101T000000Z", "20240102T000000Z",
                  "20240103T000000Z", "20240104T000000Z", "20240105T000000Z"]
        _fabricate_backups(store, stamps)
        pruned = backup.prune_backups(store, keep=2)
        assert len(pruned) == 3
        remaining = [obj.key for obj in backup.list_backups(store)]
        assert remaining == [
            "backups/20240104T000000Z.dump",
            "backups/20240105T000000Z.dump",
        ]

    def test_list_ignores_non_backup_objects(self, tmp_path):
        store = LocalArtifactStore(tmp_path)
        store.put("backups/20240101T000000Z.dump", b"x")
        store.put("1/job/doc/file.pdf", b"y")
        keys = [obj.key for obj in backup.list_backups(store)]
        assert keys == ["backups/20240101T000000Z.dump"]

    def test_list_reports_size(self, tmp_path):
        store = LocalArtifactStore(tmp_path)
        store.put("backups/20240101T000000Z.dump", b"12345")
        (only,) = backup.list_backups(store)
        assert only.size == 5
        assert isinstance(only.modified, datetime)


# ── Optional pg_dump integration ──────────────────────────────────────

def _pg_dump_available() -> bool:
    try:
        backup._resolve_pg_dump()
        return True
    except backup.BackupError:
        return False


@pytest.mark.skipif(not _pg_dump_available(), reason="pg_dump not installed")
class TestBackupIntegration:

    def test_create_backup_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
        store = LocalArtifactStore(tmp_path)
        key = backup.create_backup(store)
        assert key.startswith("backups/") and key.endswith(".dump")
        assert store.exists(key)
        (only,) = backup.list_backups(store)
        assert only.key == key
        assert only.size > 0
