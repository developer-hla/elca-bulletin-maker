"""Tests for durable DB-backed sessions and the auth token flows."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from bulletin_maker.exceptions import BulletinError
from bulletin_maker.web import auth_flows, db, email, security
from bulletin_maker.web.server import create_app
from bulletin_maker.web.sessions import SESSION_COOKIE, hash_token

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
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    email.sent_for_tests.clear()
    yield
    email.sent_for_tests.clear()


@pytest.fixture()
def client():
    with TestClient(create_app()) as tc:
        yield tc


def _register(client, **overrides):
    payload = dict(REG)
    payload.update(overrides)
    return client.post("/api/register", json=payload)


def _token_from_email(marker: str) -> str:
    body = email.sent_for_tests[-1]["text"]
    return body.split(marker)[1].split()[0]


class TestDurableSessions:

    def test_session_survives_restart(self, client):
        assert _register(client).status_code == 200
        cookie = client.cookies.get(SESSION_COOKIE)
        assert cookie
        with TestClient(create_app()) as fresh:
            fresh.cookies.set(SESSION_COOKIE, cookie)
            who = fresh.get("/api/session").json()
        assert who["authenticated"] is True
        assert who["user"]["email"] == REG["email"]

    def test_login_persists_hashed_token_only(self, client):
        _register(client)
        cookie = client.cookies.get(SESSION_COOKIE)
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT token_hash FROM sessions").fetchall()
        hashes = {r["token_hash"] for r in rows}
        assert hash_token(cookie) in hashes
        assert cookie not in hashes

    def test_logout_deletes_row(self, client):
        _register(client)
        client.delete("/api/session")
        with db.connect() as conn:
            n = conn.execute(
                "SELECT count(*) AS n FROM sessions").fetchone()["n"]
        assert n == 0
        assert client.get("/api/session").json()["authenticated"] is False

    def test_invalid_cookie_is_anonymous(self, client):
        client.cookies.set(SESSION_COOKIE, "not-a-real-token")
        assert client.get("/api/session").json()["authenticated"] is False


class TestEmailVerification:

    def test_register_sends_verification(self, client):
        _register(client)
        assert len(email.sent_for_tests) == 1
        msg = email.sent_for_tests[0]
        assert msg["to"] == REG["email"]
        assert "#verify=" in msg["text"]

    def test_verify_marks_user_and_is_single_use(self, client):
        _register(client)
        token = _token_from_email("#verify=")
        assert db.get_user_by_email(REG["email"])["email_verified"] is False
        resp = client.post("/api/auth/verify", json={"token": token})
        assert resp.status_code == 200
        assert db.get_user_by_email(REG["email"])["email_verified"] is True
        again = client.post("/api/auth/verify", json={"token": token})
        assert again.status_code == 400

    def test_verify_via_get(self, client):
        _register(client)
        token = _token_from_email("#verify=")
        resp = client.get("/api/auth/verify", params={"token": token})
        assert resp.status_code == 200
        assert db.get_user_by_email(REG["email"])["email_verified"] is True

    def test_unverified_user_can_still_use_app(self, client):
        _register(client)
        assert client.get("/api/church").status_code == 200


class TestPasswordReset:

    def _request_reset(self, client):
        email.sent_for_tests.clear()
        client.post("/api/auth/forgot", json={"email": REG["email"]})
        return _token_from_email("#reset=")

    def test_forgot_unknown_email_is_silent_success(self, client):
        _register(client)
        email.sent_for_tests.clear()
        resp = client.post("/api/auth/forgot",
                           json={"email": "ghost@nowhere.org"})
        assert resp.status_code == 200
        assert email.sent_for_tests == []

    def test_reset_changes_password(self, client):
        _register(client)
        token = self._request_reset(client)
        new_pw = "brand-new-password-9"
        resp = client.post("/api/auth/reset",
                           json={"token": token, "new_password": new_pw})
        assert resp.status_code == 200
        client.cookies.clear()
        old = client.post("/api/session", json={
            "email": REG["email"], "password": REG["password"]})
        assert old.status_code == 401
        new = client.post("/api/session", json={
            "email": REG["email"], "password": new_pw})
        assert new.status_code == 200

    def test_reset_token_is_single_use(self, client):
        _register(client)
        token = self._request_reset(client)
        first = client.post("/api/auth/reset", json={
            "token": token, "new_password": "brand-new-password-9"})
        assert first.status_code == 200
        second = client.post("/api/auth/reset", json={
            "token": token, "new_password": "another-password-8"})
        assert second.status_code == 400

    def test_reset_invalidates_existing_sessions(self, client):
        _register(client)
        token = self._request_reset(client)
        client.post("/api/auth/reset", json={
            "token": token, "new_password": "brand-new-password-9"})
        # the registration session cookie is still set on the client but
        # its row was deleted by the reset
        assert client.get("/api/session").json()["authenticated"] is False

    def test_reset_rejects_short_password(self, client):
        _register(client)
        token = self._request_reset(client)
        resp = client.post("/api/auth/reset",
                           json={"token": token, "new_password": "short"})
        assert resp.status_code == 422

    def test_reset_link_uses_app_base_url(self, client, monkeypatch):
        monkeypatch.setenv("APP_BASE_URL", "https://bulletins.example.org")
        _register(client)
        email.sent_for_tests.clear()
        client.post("/api/auth/forgot", json={"email": REG["email"]})
        body = email.sent_for_tests[-1]["text"]
        assert "https://bulletins.example.org/#reset=" in body


class TestMagicLink:

    def test_magic_link_signs_in(self, client):
        _register(client)
        client.delete("/api/session")
        email.sent_for_tests.clear()
        client.post("/api/auth/magic", json={"email": REG["email"]})
        token = _token_from_email("#magic=")
        resp = client.post("/api/auth/magic/consume", json={"token": token})
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == REG["email"]
        assert client.get("/api/session").json()["authenticated"] is True

    def test_magic_token_single_use(self, client):
        _register(client)
        email.sent_for_tests.clear()
        client.post("/api/auth/magic", json={"email": REG["email"]})
        token = _token_from_email("#magic=")
        assert client.post("/api/auth/magic/consume",
                           json={"token": token}).status_code == 200
        assert client.post("/api/auth/magic/consume",
                           json={"token": token}).status_code == 400

    def test_magic_unknown_email_is_silent_success(self, client):
        _register(client)
        email.sent_for_tests.clear()
        resp = client.post("/api/auth/magic",
                           json={"email": "ghost@nowhere.org"})
        assert resp.status_code == 200
        assert email.sent_for_tests == []


class TestEmailProvider:

    def test_console_is_default(self):
        email.send_email("to@church.app", "Hi", "Body text")
        assert email.sent_for_tests[-1]["subject"] == "Hi"

    def test_resend_requires_config(self, monkeypatch):
        monkeypatch.setenv("EMAIL_PROVIDER", "resend")
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        monkeypatch.delenv("EMAIL_FROM", raising=False)
        with pytest.raises(BulletinError):
            email.send_email("to@church.app", "Hi", "Body")

    def test_resend_posts_expected_payload(self, monkeypatch):
        monkeypatch.setenv("EMAIL_PROVIDER", "resend")
        monkeypatch.setenv("RESEND_API_KEY", "key_123")
        monkeypatch.setenv("EMAIL_FROM", "noreply@church.app")
        captured = {}

        class FakeResp:
            def raise_for_status(self):
                return None

        def fake_post(url, json, headers, timeout):
            captured.update(url=url, json=json, headers=headers)
            return FakeResp()

        monkeypatch.setattr(httpx, "post", fake_post)
        email.send_email("to@church.app", "Subject", "Body")
        assert captured["url"] == "https://api.resend.com/emails"
        assert captured["json"]["from"] == "noreply@church.app"
        assert captured["json"]["to"] == ["to@church.app"]
        assert captured["headers"]["Authorization"] == "Bearer key_123"

    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setenv("EMAIL_PROVIDER", "smoke-signal")
        with pytest.raises(BulletinError):
            email.send_email("to@church.app", "Hi", "Body")


class TestTokenRateLimit:

    def test_forgot_rate_limited_when_hosted(self, monkeypatch):
        monkeypatch.setenv("BULLETIN_HOSTED", "1")
        with TestClient(create_app()) as tc:
            for _ in range(10):
                tc.post("/api/auth/forgot", json={"email": "x@y.org"})
            resp = tc.post("/api/auth/forgot", json={"email": "x@y.org"})
        assert resp.status_code == 429
