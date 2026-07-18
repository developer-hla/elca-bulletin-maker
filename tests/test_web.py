"""Tests for the FastAPI web adapter."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from bulletin_maker.exceptions import AuthError
from bulletin_maker.sns.models import DayContent, HymnLyrics, Reading
from bulletin_maker.web.server import create_app


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


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as tc:
        yield tc


def _mock_sns(monkeypatch):
    """Patch SundaysClient inside the session module with a MagicMock."""
    instance = MagicMock()
    instance.get_day_texts.return_value = _day()
    instance.fetch_hymn_lyrics.return_value = HymnLyrics(
        number="ELW 504", title="A Mighty Fortress",
        verses=["1\tA mighty fortress is our God"], copyright="PD",
    )
    instance.search_hymn.return_value = [MagicMock(atom_id="1")]
    monkeypatch.setattr(
        "bulletin_maker.web.sessions.SundaysClient", lambda: instance)
    return instance


class TestProfileAndPrefaces:

    def test_profile(self, client):
        resp = client.get("/api/profile")
        assert resp.status_code == 200
        assert resp.json()["church_name"] == "Ascension Lutheran Church"

    def test_prefaces(self, client):
        resp = client.get("/api/prefaces")
        assert "seasonal" in resp.json()["prefaces"]


class TestSessionFlow:

    def test_login_success_sets_cookie(self, client, monkeypatch):
        _mock_sns(monkeypatch)
        resp = client.post("/api/session",
                           json={"username": "u", "password": "p"})
        assert resp.status_code == 200
        assert "bulletin_session" in resp.cookies

    def test_login_failure_401(self, client, monkeypatch):
        instance = _mock_sns(monkeypatch)
        instance.login.side_effect = AuthError("bad credentials")
        resp = client.post("/api/session",
                           json={"username": "u", "password": "wrong"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["auth_error"] is True

    def test_logout(self, client, monkeypatch):
        _mock_sns(monkeypatch)
        client.post("/api/session", json={"username": "u", "password": "p"})
        resp = client.delete("/api/session")
        assert resp.json()["success"] is True


class TestDayContent:

    def test_fetch_day_returns_defaults_and_warnings(self, client, monkeypatch):
        _mock_sns(monkeypatch)
        client.post("/api/session", json={"username": "u", "password": "p"})
        resp = client.get("/api/day",
                          params={"date": "2026-07-19", "display": "July 19, 2026"})
        body = resp.json()
        assert body["day_name"] == "Lectionary 16"
        assert body["season"] == "pentecost"
        assert body["warnings"] == []
        assert body["defaults"]["eucharistic_form"] == "short"
        assert body["prefix"] == "2026.07.19 - Lectionary 16 Year A"

    def test_bad_date_422(self, client):
        resp = client.get("/api/day",
                          params={"date": "07/19/2026", "display": "x"})
        assert resp.status_code == 422

    def test_texts_requires_fetched_day(self, client):
        resp = client.get("/api/day/texts")
        assert resp.status_code == 409

    def test_texts_and_preview_after_fetch(self, client, monkeypatch):
        _mock_sns(monkeypatch)
        client.post("/api/session", json={"username": "u", "password": "p"})
        client.get("/api/day",
                   params={"date": "2026-07-19", "display": "July 19, 2026"})
        texts = client.get("/api/day/texts").json()["texts"]
        assert "confession" in texts and "dismissal" in texts
        preview = client.get("/api/day/readings/first/preview").json()
        assert preview["label"] == "First Reading"

    def test_unknown_preview_slot_422(self, client, monkeypatch):
        _mock_sns(monkeypatch)
        client.post("/api/session", json={"username": "u", "password": "p"})
        client.get("/api/day",
                   params={"date": "2026-07-19", "display": "July 19, 2026"})
        resp = client.get("/api/day/readings/epistle/preview")
        assert resp.status_code == 422


class TestHymns:

    def test_hymn_fetch_populates_session_cache(self, client, monkeypatch):
        _mock_sns(monkeypatch)
        client.post("/api/session", json={"username": "u", "password": "p"})
        resp = client.get("/api/hymns/ELW/504", params={"date": "2026-07-19"})
        body = resp.json()
        assert body["title"] == "A Mighty Fortress"
        assert body["verse_count"] == 1


class TestCoverUpload:

    def test_rejects_unknown_type(self, client):
        resp = client.post(
            "/api/cover", files={"file": ("evil.svg", b"<svg/>", "image/svg+xml")})
        assert resp.status_code == 422

    def test_accepts_jpeg(self, client):
        resp = client.post(
            "/api/cover", files={"file": ("rose.jpg", b"\xff\xd8fake", "image/jpeg")})
        body = resp.json()
        assert body["success"] is True
        assert body["cover_token"].endswith(".jpg")


class TestGenerationJob:

    def test_generate_without_day_409(self, client):
        resp = client.post("/api/generate", json={"date": "2026-07-19",
                                                  "date_display": "July 19"})
        assert resp.status_code == 409

    def test_job_lifecycle_with_mocked_generation(self, client, monkeypatch, tmp_path):
        _mock_sns(monkeypatch)
        client.post("/api/session", json={"username": "u", "password": "p"})
        client.get("/api/day",
                   params={"date": "2026-07-19", "display": "July 19, 2026"})

        def fake_generate(day, config, output_dir, **kwargs):
            from bulletin_maker.core.documents import GenerationResult
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress("scripture", "[1/1] Pulpit scripture saved", 95)
                on_progress("done", "Generation complete!", 100)
            pdf = output_dir / "Pulpit SCRIPTURE - test.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake")
            result = GenerationResult()
            result.results["scripture"] = str(pdf)
            return result

        with patch("bulletin_maker.web.server.generate_documents",
                   side_effect=fake_generate):
            resp = client.post("/api/generate", json={
                "date": "2026-07-19", "date_display": "July 19, 2026",
                "selected_docs": ["scripture"],
            })
            job_id = resp.json()["job_id"]

            for _ in range(50):
                status = client.get(f"/api/jobs/{job_id}").json()
                if status["status"] != "running":
                    break
                time.sleep(0.05)

        assert status["status"] == "done"
        assert status["results"] == {"scripture": "Pulpit SCRIPTURE - test.pdf"}
        assert any(p["step"] == "done" for p in status["progress"])

        pdf = client.get(f"/api/jobs/{job_id}/files/scripture")
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")

        zipped = client.get(f"/api/jobs/{job_id}/zip")
        assert zipped.status_code == 200

    def test_unknown_job_404(self, client):
        assert client.get("/api/jobs/nope").status_code == 404


class TestPastRunsEndpoints:

    def test_crud(self, client, monkeypatch, tmp_path):
        from bulletin_maker.core import past_runs
        monkeypatch.setattr(past_runs, "_path",
                            lambda: tmp_path / "past_runs.json")
        save = client.post("/api/runs", json={
            "form_data": {"date": "2026-07-19"},
            "metadata": {"day_name": "Lectionary 16"},
        }).json()
        run_id = save["id"]
        assert client.get("/api/runs").json()["runs"][0]["id"] == run_id
        assert client.get(f"/api/runs/{run_id}").json()["form_data"]["date"] == "2026-07-19"
        assert client.delete(f"/api/runs/{run_id}").json()["success"] is True
        assert client.get(f"/api/runs/{run_id}").status_code == 404


class TestSpa:

    def test_index_served_at_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Bulletin Maker" in resp.text


class TestHostedHardening:

    def test_rate_limiter_blocks_after_limit(self):
        from bulletin_maker.web.server import LoginRateLimiter
        limiter = LoginRateLimiter(limit=3, window=60)
        assert all(limiter.check("1.2.3.4") for _ in range(3))
        assert limiter.check("1.2.3.4") is False
        assert limiter.check("5.6.7.8") is True  # other addresses unaffected

    def test_hosted_login_rate_limited(self, monkeypatch):
        monkeypatch.setenv("BULLETIN_HOSTED", "1")
        app = create_app()
        instance = MagicMock()
        instance.login.side_effect = AuthError("nope")
        monkeypatch.setattr(
            "bulletin_maker.web.sessions.SundaysClient", lambda: instance)
        with TestClient(app) as tc:
            for _ in range(10):
                tc.post("/api/session", json={"username": "u", "password": "x"})
            resp = tc.post("/api/session", json={"username": "u", "password": "x"})
        assert resp.status_code == 429

    def test_profile_env_override(self, monkeypatch, tmp_path):
        from bulletin_maker.core.profile import load_profile
        other = tmp_path / "other.toml"
        other.write_text(
            '[church]\nname = "St. Test"\naddress_lines = ["x"]\n'
            'service_time = "9:00 AM"\n[texts]\nwelcome_message = "hi"\n'
            'standing_instructions = "stand"\n'
        )
        monkeypatch.setenv("BULLETIN_PROFILE", str(other))
        assert load_profile().church_name == "St. Test"

    def test_session_close_removes_job_dirs(self, tmp_path):
        from bulletin_maker.web.sessions import Session
        job_dir = tmp_path / "job1"
        job_dir.mkdir()
        (job_dir / "out.pdf").write_bytes(b"%PDF")
        session = Session(id="s1")
        session.jobs["j1"] = {"dir": str(job_dir)}
        session.close()
        assert not job_dir.exists()
