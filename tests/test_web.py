"""Tests for the FastAPI web adapter — accounts, church scoping, jobs."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from bulletin_maker.exceptions import AuthError
from bulletin_maker.sns.models import DayContent, HymnLyrics, Reading
from bulletin_maker.web import security
from bulletin_maker.web.server import create_app

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
    monkeypatch.setenv("BULLETIN_DB", str(tmp_path / "app.db"))
    monkeypatch.setattr(security, "KEYFILE", tmp_path / "secret.key")
    monkeypatch.delenv("BULLETIN_SECRET_KEY", raising=False)
    monkeypatch.delenv("BULLETIN_REGISTRATION_CODE", raising=False)
    monkeypatch.delenv("BULLETIN_HOSTED", raising=False)


@pytest.fixture()
def client():
    with TestClient(create_app()) as tc:
        yield tc


def _mock_sns(monkeypatch):
    """Mock every SundaysClient the server creates (link probe + session)."""
    instance = MagicMock()
    instance.get_day_texts.return_value = _day()
    instance.fetch_hymn_lyrics.return_value = HymnLyrics(
        number="ELW 504", title="A Mighty Fortress",
        verses=["1\tA mighty fortress is our God"], copyright="PD",
    )
    instance.search_hymn.return_value = [MagicMock(atom_id="1", title="A Mighty Fortress")]
    monkeypatch.setattr(
        "bulletin_maker.web.server.SundaysClient", lambda: instance)
    return instance


def _register(client, **overrides):
    payload = dict(REG)
    payload.update(overrides)
    return client.post("/api/register", json=payload)


def _register_and_link(client, monkeypatch):
    instance = _mock_sns(monkeypatch)
    assert _register(client).status_code == 200
    resp = client.put("/api/church/sns-link",
                      json={"username": "church@sns.org", "password": "snspw"})
    assert resp.status_code == 200
    return instance


class TestSecurity:

    def test_password_roundtrip(self):
        stored = security.hash_password("hunter2hunter2")
        assert security.verify_password("hunter2hunter2", stored)
        assert not security.verify_password("wrong", stored)

    def test_hashes_are_salted(self):
        assert security.hash_password("same") != security.hash_password("same")

    def test_garbage_hash_rejected(self):
        assert not security.verify_password("x", "not-a-hash")

    def test_secret_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(security, "KEYFILE", tmp_path / "k.key")
        token = security.encrypt_secret("s&s-password")
        assert token != "s&s-password"
        assert security.decrypt_secret(token) == "s&s-password"

    def test_key_change_raises_clear_error(self, tmp_path, monkeypatch):
        from bulletin_maker.exceptions import BulletinError
        monkeypatch.setattr(security, "KEYFILE", tmp_path / "k1.key")
        token = security.encrypt_secret("secret")
        monkeypatch.setattr(security, "KEYFILE", tmp_path / "k2.key")
        with pytest.raises(BulletinError, match="secret key has changed"):
            security.decrypt_secret(token)


class TestRegistration:

    def test_first_church_registers_freely(self, client):
        resp = _register(client)
        body = resp.json()
        assert resp.status_code == 200
        assert body["user"]["role"] == "admin"
        assert body["church"]["name"] == "St. Test Lutheran"
        assert body["sns_linked"] is False

    def test_second_church_needs_code(self, client):
        _register(client)
        resp = _register(client, church_name="Other Church",
                         email="other@church.org")
        assert resp.status_code == 403

    def test_second_church_with_code(self, client, monkeypatch):
        _register(client)
        monkeypatch.setenv("BULLETIN_REGISTRATION_CODE", "let-me-in")
        resp = _register(client, church_name="Other Church",
                         email="other@church.org",
                         registration_code="let-me-in")
        assert resp.status_code == 200

    def test_duplicate_email_rejected(self, client, monkeypatch):
        _register(client)
        monkeypatch.setenv("BULLETIN_REGISTRATION_CODE", "code")
        resp = _register(client, church_name="Other",
                         registration_code="code")
        assert resp.status_code == 409

    def test_short_password_rejected(self, client):
        resp = _register(client, password="short")
        assert resp.status_code == 422

    def test_new_church_seeded_with_own_name(self, client):
        _register(client)
        profile = client.get("/api/church").json()["profile"]
        assert profile["church_name"] == "St. Test Lutheran"
        assert profile["liturgical_setting"] == "setting_two"

    def test_instance_info(self, client):
        assert client.get("/api/instance").json()["has_churches"] is False
        _register(client)
        info = client.get("/api/instance").json()
        assert info["has_churches"] is True
        assert info["registration_open"] is False  # no code set


class TestJoinAndLogin:

    def test_member_joins_with_invite(self, client):
        _register(client)
        invite = client.get("/api/church").json()["invite_code"]
        client.delete("/api/session")
        resp = client.post("/api/join", json={
            "invite_code": invite, "email": "vol@sttest.org",
            "password": "volunteer-pass", "display_name": "Vi Volunteer"})
        body = resp.json()
        assert resp.status_code == 200
        assert body["user"]["role"] == "member"
        assert body["church"]["name"] == "St. Test Lutheran"

    def test_bad_invite_rejected(self, client):
        _register(client)
        client.delete("/api/session")
        resp = client.post("/api/join", json={
            "invite_code": "nope", "email": "x@y.org", "password": "longenough"})
        assert resp.status_code == 403

    def test_login_logout_whoami(self, client):
        _register(client)
        client.delete("/api/session")
        assert client.get("/api/session").json()["authenticated"] is False
        resp = client.post("/api/session", json={
            "email": REG["email"], "password": REG["password"]})
        assert resp.status_code == 200
        who = client.get("/api/session").json()
        assert who["authenticated"] is True
        assert who["user"]["email"] == REG["email"]

    def test_wrong_password_401(self, client):
        _register(client)
        client.delete("/api/session")
        resp = client.post("/api/session", json={
            "email": REG["email"], "password": "incorrect-pass"})
        assert resp.status_code == 401

    def test_protected_endpoints_require_login(self, client):
        resp = client.get("/api/day",
                          params={"date": "2026-07-19", "display": "x"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["auth_error"] is True


class TestSnsLink:

    def test_link_validates_and_stores(self, client, monkeypatch):
        instance = _register_and_link(client, monkeypatch)
        instance.login.assert_called_with("church@sns.org", "snspw")
        settings = client.get("/api/church").json()
        assert settings["sns_linked"] is True
        assert settings["sns_username"] == "church@sns.org"

    def test_bad_sns_credential_not_stored(self, client, monkeypatch):
        instance = _mock_sns(monkeypatch)
        instance.login.side_effect = AuthError("bad")
        _register(client)
        resp = client.put("/api/church/sns-link",
                          json={"username": "u", "password": "wrong"})
        assert resp.status_code == 401
        assert client.get("/api/church").json()["sns_linked"] is False

    def test_member_cannot_link(self, client, monkeypatch):
        _mock_sns(monkeypatch)
        _register(client)
        invite = client.get("/api/church").json()["invite_code"]
        client.delete("/api/session")
        client.post("/api/join", json={
            "invite_code": invite, "email": "vol@sttest.org",
            "password": "volunteer-pass"})
        resp = client.put("/api/church/sns-link",
                          json={"username": "u", "password": "p"})
        assert resp.status_code == 403

    def test_fetch_without_link_says_so(self, client, monkeypatch):
        _mock_sns(monkeypatch)
        _register(client)
        resp = client.get("/api/day",
                          params={"date": "2026-07-19", "display": "x"})
        assert resp.status_code == 409
        assert resp.json()["detail"]["sns_unlinked"] is True


class TestChurchProfile:

    def test_update_profile_bounded_options(self, client):
        _register(client)
        resp = client.put("/api/church/profile", json={
            "service_time": "9:30 AM", "liturgical_setting": "setting_three"})
        assert resp.status_code == 200
        profile = client.get("/api/church").json()["profile"]
        assert profile["service_time"] == "9:30 AM"
        assert profile["liturgical_setting"] == "setting_three"

    def test_invalid_setting_rejected(self, client):
        _register(client)
        resp = client.put("/api/church/profile",
                          json={"liturgical_setting": "setting_ninety"})
        assert resp.status_code == 422

    def test_options_lists_included(self, client):
        _register(client)
        options = client.get("/api/church").json()["options"]
        keys = {o["key"] for o in options["liturgical_setting"]}
        assert "setting_one" in keys and "setting_five" in keys
        assert {o["key"] for o in options["paper_size"]} == {
            "legal_booklet", "letter_booklet", "a4_booklet"}

    def test_member_cannot_edit_profile(self, client, monkeypatch):
        _register(client)
        invite = client.get("/api/church").json()["invite_code"]
        client.delete("/api/session")
        client.post("/api/join", json={
            "invite_code": invite, "email": "vol@sttest.org",
            "password": "volunteer-pass"})
        resp = client.put("/api/church/profile", json={"service_time": "8 AM"})
        assert resp.status_code == 403
        # and members don't see the invite code
        settings = client.get("/api/church").json()
        assert "invite_code" not in settings


class TestDayAndGeneration:

    def test_day_fetch_with_linked_account(self, client, monkeypatch):
        _register_and_link(client, monkeypatch)
        resp = client.get("/api/day",
                          params={"date": "2026-07-19", "display": "July 19, 2026"})
        body = resp.json()
        assert body["day_name"] == "Lectionary 16"
        assert body["warnings"] == []

    def test_generation_uses_church_profile(self, client, monkeypatch, tmp_path):
        _register_and_link(client, monkeypatch)
        client.put("/api/church/profile", json={"service_time": "8:15 AM"})
        client.get("/api/day",
                   params={"date": "2026-07-19", "display": "July 19, 2026"})

        captured = {}

        def fake_generate(day, config, output_dir, **kwargs):
            from bulletin_maker.core.documents import GenerationResult
            captured["profile"] = kwargs.get("profile")
            pdf = output_dir / "out.pdf"
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
            for _ in range(50):
                status = client.get(f"/api/jobs/{job_id}").json()
                if status["status"] != "running":
                    break
                time.sleep(0.05)
        assert status["status"] == "done"
        assert captured["profile"].service_time == "8:15 AM"
        assert captured["profile"].church_name == "St. Test Lutheran"


class TestChurchIsolation:

    def test_past_runs_scoped_per_church(self, client, monkeypatch):
        _register(client)
        client.post("/api/runs", json={
            "form_data": {"date": "2026-07-19"},
            "metadata": {"day_name": "Lectionary 16"}})
        run_id = client.get("/api/runs").json()["runs"][0]["id"]

        # second church cannot see or fetch it
        monkeypatch.setenv("BULLETIN_REGISTRATION_CODE", "code")
        client.delete("/api/session")
        _register(client, church_name="Other Church", email="o@other.org",
                  registration_code="code")
        assert client.get("/api/runs").json()["runs"] == []
        assert client.get(f"/api/runs/{run_id}").status_code == 404


class TestHostedRateLimit:

    def test_login_rate_limited_when_hosted(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BULLETIN_DB", str(tmp_path / "rl.db"))
        monkeypatch.setenv("BULLETIN_HOSTED", "1")
        with TestClient(create_app()) as tc:
            for _ in range(10):
                tc.post("/api/session",
                        json={"email": "x@y.org", "password": "wrongwrong"})
            resp = tc.post("/api/session",
                           json={"email": "x@y.org", "password": "wrongwrong"})
        assert resp.status_code == 429


class TestSpa:

    def test_index_served_at_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Bulletin Maker" in resp.text
