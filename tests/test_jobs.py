"""Tests for durable jobs, the artifact store, and restart survival."""

from __future__ import annotations

import io
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from bulletin_maker.core.documents import GenerationResult
from bulletin_maker.exceptions import BulletinError
from bulletin_maker.sns.models import DayContent, HymnLyrics, Reading
from bulletin_maker.web import artifacts, db, jobstore, security
from bulletin_maker.web.artifacts import (
    LocalArtifactStore,
    S3ArtifactStore,
    get_store,
)
from bulletin_maker.web.server import RESTART_JOB_MESSAGE, create_app

TEST_DATABASE_URL = "postgresql://localhost/bulletin_maker_test"

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


def _day() -> DayContent:
    readings = [
        Reading(label=label, citation=f"{label[:4]} 1:1", intro="intro",
                text_html="<p>text</p>")
        for label in ("First Reading", "Psalm", "Second Reading", "Gospel")
    ]
    return DayContent(
        date="2026-7-19",
        title="Sunday, July 19, 2026 Lectionary 16, Year A",
        introduction="", confession_html="<div>c</div>",
        prayer_of_the_day_html="<p>p</p>", gospel_acclamation="ga",
        readings=readings, prayers_html="<p>prayers</p>",
        offering_prayer_html="o", prayer_after_communion_html="pac",
        blessing_html="b", dismissal_html="d",
    )


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
    monkeypatch.delenv("BULLETIN_REGISTRATION_CODE", raising=False)
    monkeypatch.delenv("BULLETIN_HOSTED", raising=False)
    monkeypatch.setenv("ARTIFACT_STORE", "local")
    monkeypatch.setenv("BULLETIN_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    for name in ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY_ID",
                 "S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def client():
    with TestClient(create_app()) as tc:
        yield tc


def _mock_sns(monkeypatch):
    instance = MagicMock()
    instance.get_day_texts.return_value = _day()
    instance.fetch_hymn_lyrics.return_value = HymnLyrics(
        number="ELW 504", title="A Mighty Fortress",
        verses=["1\tA mighty fortress is our God"], copyright="PD")
    instance.search_hymn.return_value = [
        MagicMock(atom_id="1", title="A Mighty Fortress")]
    monkeypatch.setattr(
        "bulletin_maker.web.server.SundaysClient", lambda: instance)
    return instance


def _register(client, **overrides):
    payload = dict(REG)
    payload.update(overrides)
    return client.post("/api/register", json=payload)


def _prepare(client, monkeypatch, **overrides):
    """Register, link S&S, and fetch a day so generation can run."""
    _mock_sns(monkeypatch)
    assert _register(client, **overrides).status_code == 200
    resp = client.put("/api/church/sns-link",
                      json={"username": "church@sns.org", "password": "pw"})
    assert resp.status_code == 200
    resp = client.get("/api/day",
                      params={"date": "2026-07-19", "display": "July 19, 2026"})
    assert resp.status_code == 200


def _fake_generate_factory(doc_key="scripture", body=b"%PDF-1.4 fake"):
    def fake_generate(day, config, output_dir, **kwargs):
        pdf = output_dir / f"{doc_key}.pdf"
        pdf.write_bytes(body)
        result = GenerationResult()
        result.results[doc_key] = str(pdf)
        return result
    return fake_generate


def _run_to_done(client, doc_key="scripture", body=b"%PDF-1.4 fake"):
    with patch("bulletin_maker.web.server.generate_documents",
               side_effect=_fake_generate_factory(doc_key, body)):
        resp = client.post("/api/generate", json={
            "date": "2026-07-19", "date_display": "July 19, 2026",
            "selected_docs": [doc_key]})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        status = {}
        for _ in range(100):
            status = client.get(f"/api/jobs/{job_id}").json()
            if status["status"] != "running":
                break
            time.sleep(0.05)
    assert status["status"] == "done", status
    return job_id


# ── Local store ──────────────────────────────────────────────────────

class TestLocalStore:

    def test_roundtrip_bytes_and_path(self, tmp_path):
        store = LocalArtifactStore(tmp_path / "store")
        assert store.put("a/b/one.pdf", b"hello") == 5
        assert store.exists("a/b/one.pdf")
        stream = store.open_stream("a/b/one.pdf")
        try:
            assert stream.read() == b"hello"
        finally:
            stream.close()
        src = tmp_path / "src.pdf"
        src.write_bytes(b"from-path")
        store.put("c/two.pdf", src)
        assert store.exists("c/two.pdf")

    def test_delete_is_idempotent(self, tmp_path):
        store = LocalArtifactStore(tmp_path / "store")
        store.put("x.pdf", b"z")
        store.delete("x.pdf")
        store.delete("x.pdf")  # missing is not an error
        assert not store.exists("x.pdf")

    def test_get_store_defaults_to_local(self):
        assert isinstance(get_store(), LocalArtifactStore)


# ── S3 store (fake boto3 client) ─────────────────────────────────────

class _FakeBoto:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def head_object(self, Bucket, Key):
        from botocore.exceptions import ClientError
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}


class TestS3Store:

    def test_roundtrip(self):
        store = S3ArtifactStore(_FakeBoto(), "bucket")
        assert store.put("k/one.pdf", b"data") == 4
        assert store.exists("k/one.pdf")
        stream = store.open_stream("k/one.pdf")
        assert stream.read() == b"data"
        store.delete("k/one.pdf")
        assert not store.exists("k/one.pdf")

    def test_missing_config_fails_fast(self, monkeypatch):
        monkeypatch.setenv("ARTIFACT_STORE", "s3")
        with pytest.raises(BulletinError, match="S3_BUCKET"):
            get_store()

    def test_unknown_backend_rejected(self, monkeypatch):
        monkeypatch.setenv("ARTIFACT_STORE", "gopher")
        with pytest.raises(BulletinError, match="Unknown ARTIFACT_STORE"):
            get_store()


# ── TTL purge ────────────────────────────────────────────────────────

class TestPurge:

    def _seed_job(self):
        church = db.create_church("St. Purge", {"church_name": "St. Purge"})
        jobstore.create_job("job-purge", church["id"], None, {})
        return church["id"]

    def test_purge_deletes_expired_only(self):
        self._seed_job()
        store = get_store()
        store.put("keep.pdf", b"keep")
        store.put("gone.pdf", b"gone")
        future = datetime.now(timezone.utc) + timedelta(days=1)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        artifacts.record_artifact("job-purge", "a", "keep.pdf", "keep.pdf",
                                  4, future)
        artifacts.record_artifact("job-purge", "b", "gone.pdf", "gone.pdf",
                                  4, past)

        assert artifacts.purge_expired_artifacts() == 1
        assert store.exists("keep.pdf")
        assert not store.exists("gone.pdf")
        assert len(artifacts.artifacts_for_job("job-purge")) == 1

    def test_purge_noop_when_nothing_expired(self):
        assert artifacts.purge_expired_artifacts() == 0


# ── End-to-end generation, persistence, download ─────────────────────

class TestGenerationJobs:

    def test_job_and_artifacts_persisted(self, client, monkeypatch):
        _prepare(client, monkeypatch)
        job_id = _run_to_done(client)

        with db.connect() as conn:
            row = conn.execute(
                "SELECT status, results_jsonb FROM jobs WHERE id = %s",
                (job_id,)).fetchone()
        assert row["status"] == "done"
        assert row["results_jsonb"] == {"scripture": "scripture.pdf"}
        rows = artifacts.artifacts_for_job(job_id)
        assert len(rows) == 1
        assert rows[0]["object_key"].endswith(f"/{job_id}/scripture/scripture.pdf")
        assert rows[0]["expires_at"] > datetime.now(timezone.utc)

    def test_progress_shape_preserved(self, client, monkeypatch):
        _prepare(client, monkeypatch)

        def fake_generate(day, config, output_dir, **kwargs):
            kwargs["on_progress"]("scripture", "Rendering scripture", 50)
            pdf = output_dir / "scripture.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake")
            result = GenerationResult()
            result.results["scripture"] = str(pdf)
            return result

        with patch("bulletin_maker.web.server.generate_documents",
                   side_effect=fake_generate):
            resp = client.post("/api/generate", json={
                "date": "2026-07-19", "date_display": "July 19, 2026",
                "selected_docs": ["scripture"]})
            job_id = resp.json()["job_id"]
            status = {}
            for _ in range(100):
                status = client.get(f"/api/jobs/{job_id}").json()
                if status["status"] != "running":
                    break
                time.sleep(0.05)
        assert status["progress"][0] == {
            "step": "scripture", "detail": "Rendering scripture", "pct": 50}

    def test_download_streams_file(self, client, monkeypatch):
        _prepare(client, monkeypatch)
        job_id = _run_to_done(client, body=b"%PDF-1.4 real-bytes")
        resp = client.get(f"/api/jobs/{job_id}/files/scripture")
        assert resp.status_code == 200
        assert resp.content == b"%PDF-1.4 real-bytes"
        assert resp.headers["content-type"] == "application/pdf"

    def test_zip_built_from_store(self, client, monkeypatch):
        _prepare(client, monkeypatch)
        job_id = _run_to_done(client)
        resp = client.get(f"/api/jobs/{job_id}/zip")
        assert resp.status_code == 200
        import zipfile
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        assert zf.namelist() == ["scripture.pdf"]

    def test_download_survives_restart(self, client, monkeypatch):
        _prepare(client, monkeypatch)
        job_id = _run_to_done(client, body=b"%PDF-1.4 durable")

        # A fresh app == a server restart: new in-memory session store,
        # same database and artifact directory.
        with TestClient(create_app()) as restarted:
            login = restarted.post("/api/session", json={
                "email": REG["email"], "password": REG["password"]})
            assert login.status_code == 200
            resp = restarted.get(f"/api/jobs/{job_id}/files/scripture")
            assert resp.status_code == 200
            assert resp.content == b"%PDF-1.4 durable"
            status = restarted.get(f"/api/jobs/{job_id}").json()
            assert status["status"] == "done"

    def test_job_is_church_scoped(self, client, monkeypatch):
        _prepare(client, monkeypatch)
        job_id = _run_to_done(client)

        monkeypatch.setenv("BULLETIN_REGISTRATION_CODE", "code")
        client.delete("/api/session")
        _register(client, church_name="Other Church", email="o@other.org",
                  registration_code="code")
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        assert client.get(
            f"/api/jobs/{job_id}/files/scripture").status_code == 404


# ── Backend-swap wiring (in-memory stub) ─────────────────────────────

class _MemoryStore:
    def __init__(self):
        self.objects = {}

    def put(self, object_key, source):
        data = source if isinstance(source, bytes) else open(source, "rb").read()
        self.objects[object_key] = data
        return len(data)

    def open_stream(self, object_key):
        return io.BytesIO(self.objects[object_key])

    def delete(self, object_key):
        self.objects.pop(object_key, None)

    def exists(self, object_key):
        return object_key in self.objects


class TestBackendSwap:

    def test_generation_uses_configured_backend(self, client, monkeypatch):
        _prepare(client, monkeypatch)
        memory = _MemoryStore()
        monkeypatch.setattr(artifacts, "get_store", lambda: memory)
        job_id = _run_to_done(client, body=b"%PDF-1.4 memory")
        assert any(v == b"%PDF-1.4 memory" for v in memory.objects.values())
        resp = client.get(f"/api/jobs/{job_id}/files/scripture")
        assert resp.content == b"%PDF-1.4 memory"


# ── Boot recovery ────────────────────────────────────────────────────

class TestBootRecovery:

    def test_stale_jobs_failed_on_startup(self, monkeypatch):
        church = db.create_church("St. Crash", {"church_name": "St. Crash"})
        jobstore.create_job("stuck", church["id"], None, {})
        with db.connect() as conn:
            conn.execute("UPDATE jobs SET status = 'running' WHERE id = 'stuck'")

        with TestClient(create_app()):
            pass  # lifespan startup runs recovery

        job = jobstore.get_job("stuck", church["id"])
        assert job["status"] == "failed"
        assert job["errors_jsonb"] == {"job": RESTART_JOB_MESSAGE}
