"""Tests for the cross-church operator console (WS-7)."""

from __future__ import annotations

import os
import secrets

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from bulletin_maker.web import db, email, security
from bulletin_maker.web.server import create_app
from bulletin_maker.web.sessions import SESSION_COOKIE

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
    monkeypatch.delenv("BULLETIN_REGISTRATION_CODE", raising=False)
    monkeypatch.delenv("BULLETIN_HOSTED", raising=False)
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    email.sent_for_tests.clear()
    yield
    email.sent_for_tests.clear()


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app) as tc:
        yield tc


def _register(client, **overrides):
    payload = dict(REG)
    payload.update(overrides)
    return client.post("/api/register", json=payload)


def _grant_operator(email_address: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET operator = true WHERE email = %s",
            (email_address,))


def _register_operator(client):
    """Register the first church and promote its admin to operator."""
    resp = _register(client)
    assert resp.status_code == 200
    _grant_operator(REG["email"])
    # Re-fetch so the session carries the operator flag on whoami
    return client.get("/api/session").json()


def _second_church(other_client, monkeypatch, **overrides):
    monkeypatch.setenv("BULLETIN_REGISTRATION_CODE", "let-me-in")
    payload = {
        "church_name": "Other Church",
        "email": "vol@other.org",
        "password": "other-good-password",
        "display_name": "Ollie Other",
        "registration_code": "let-me-in",
    }
    payload.update(overrides)
    resp = other_client.post("/api/register", json=payload)
    assert resp.status_code == 200
    return resp.json()


def _insert_job(church_id: int, status: str = "done") -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, church_id, status) VALUES (%s, %s, %s)",
            (secrets.token_hex(8), church_id, status))


def _insert_failed_job(church_id: int, message: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, church_id, status, errors_jsonb)"
            " VALUES (%s, %s, 'failed', %s)",
            (secrets.token_hex(8), church_id, Jsonb({"job": message})))


def _insert_cache(cache_key: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sns_cache (cache_key, payload_jsonb) VALUES (%s, %s)",
            (cache_key, Jsonb({"x": 1})))


class TestRequireOperator:

    def test_regular_admin_forbidden(self, client):
        _register(client)
        assert client.get("/api/operator/churches").status_code == 403

    def test_member_forbidden(self, client, app, monkeypatch):
        _register(client)
        invite = client.get("/api/church").json()["invite_code"]
        with TestClient(app) as member:
            member.post("/api/join", json={
                "invite_code": invite, "email": "m@sttest.org",
                "password": "member-good-password"})
            assert member.get("/api/operator/jobs").status_code == 403

    def test_anonymous_unauthorized(self, client):
        assert client.get("/api/operator/audit").status_code == 401

    def test_operator_allowed(self, client):
        _register_operator(client)
        resp = client.get("/api/operator/churches")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_whoami_exposes_operator_flag(self, client):
        who = _register_operator(client)
        assert who["operator"] is True


class TestRoster:

    def test_roster_shape_and_cross_church_counts(self, client, app,
                                                  monkeypatch):
        _register_operator(client)
        invite = client.get("/api/church").json()["invite_code"]
        with TestClient(app) as member:
            member.post("/api/join", json={
                "invite_code": invite, "email": "m@sttest.org",
                "password": "member-good-password"})
        with TestClient(app) as other:
            _second_church(other, monkeypatch)

        roster = {c["name"]: c for c in
                  client.get("/api/operator/churches").json()["churches"]}
        st = roster["St. Test Lutheran"]
        other = roster["Other Church"]
        assert st["member_count"] == 2   # admin + member
        assert other["member_count"] == 1
        expected_keys = {"id", "name", "plan", "disabled", "member_count",
                         "sns_linked", "last_generate_at",
                         "generates_this_month"}
        assert set(st.keys()) == expected_keys
        assert st["sns_linked"] is False
        assert st["disabled"] is False

    def test_roster_never_exposes_sns_username(self, client):
        _register_operator(client)
        body = client.get("/api/operator/churches").text
        assert "sns_username" not in body
        assert "sns_password" not in body

    def test_generate_counts_and_last_generate(self, client):
        _register_operator(client)
        church_id = client.get(
            "/api/operator/churches").json()["churches"][0]["id"]
        _insert_job(church_id)
        _insert_job(church_id)
        st = client.get("/api/operator/churches").json()["churches"][0]
        assert st["generates_this_month"] == 2
        assert st["last_generate_at"] is not None


class TestDisableEnable:

    def test_disable_blocks_login_and_session(self, client, app, monkeypatch):
        _register_operator(client)
        with TestClient(app) as other:
            _second_church(other, monkeypatch)
            assert other.get("/api/session").json()["authenticated"] is True
            other_id = {c["name"]: c["id"] for c in client.get(
                "/api/operator/churches").json()["churches"]}["Other Church"]

            disable = client.post(
                f"/api/operator/churches/{other_id}/disable")
            assert disable.status_code == 200

            # In-flight session is refused
            who = other.get("/api/session")
            assert who.status_code == 401
            assert who.json()["detail"]["suspended"] is True

        # Fresh login is refused with the suspended message
        with TestClient(app) as fresh:
            login = fresh.post("/api/session", json={
                "email": "vol@other.org", "password": "other-good-password"})
            assert login.status_code == 401
            assert "suspended" in login.json()["detail"]["error"].lower()

    def test_operator_exempt_from_own_disable(self, client):
        _register_operator(client)
        own_id = client.get(
            "/api/operator/churches").json()["churches"][0]["id"]
        client.post(f"/api/operator/churches/{own_id}/disable")
        assert client.get("/api/session").status_code == 200
        assert client.get("/api/operator/churches").status_code == 200

    def test_enable_restores_access(self, client, app, monkeypatch):
        _register_operator(client)
        with TestClient(app) as other:
            _second_church(other, monkeypatch)
            other_id = {c["name"]: c["id"] for c in client.get(
                "/api/operator/churches").json()["churches"]}["Other Church"]
            client.post(f"/api/operator/churches/{other_id}/disable")
            client.post(f"/api/operator/churches/{other_id}/enable")
            assert other.get("/api/session").json()["authenticated"] is True

    def test_disable_unknown_church_404(self, client):
        _register_operator(client)
        assert client.post(
            "/api/operator/churches/9999/disable").status_code == 404


class TestResetPassword:

    def test_reset_sends_email(self, client, app, monkeypatch):
        _register_operator(client)
        with TestClient(app) as other:
            _second_church(other, monkeypatch)
        target = db.get_user_by_email("vol@other.org")
        email.sent_for_tests.clear()
        resp = client.post(
            f"/api/operator/users/{target['id']}/reset-password")
        assert resp.status_code == 200
        assert len(email.sent_for_tests) == 1
        assert email.sent_for_tests[-1]["to"] == "vol@other.org"

    def test_reset_unknown_user_404(self, client):
        _register_operator(client)
        assert client.post(
            "/api/operator/users/9999/reset-password").status_code == 404


class TestAudit:

    def test_disable_enable_reset_recorded(self, client, app, monkeypatch):
        _register_operator(client)
        with TestClient(app) as other:
            _second_church(other, monkeypatch)
        target = db.get_user_by_email("vol@other.org")
        other_id = target["church_id"]
        client.post(f"/api/operator/churches/{other_id}/disable")
        client.post(f"/api/operator/churches/{other_id}/enable")
        client.post(f"/api/operator/users/{target['id']}/reset-password")

        events = client.get("/api/operator/audit").json()["events"]
        actions = {e["action"] for e in events}
        assert "church_disabled" in actions
        assert "church_enabled" in actions
        assert "password_reset" in actions
        # registration + join lifecycle events are captured too
        assert "church_registered" in actions

    def test_audit_event_shape(self, client):
        _register_operator(client)
        events = client.get("/api/operator/audit").json()["events"]
        assert events, "expected at least the registration event"
        expected_keys = {"id", "actor_email", "church_name", "action",
                         "detail", "at"}
        assert set(events[0].keys()) == expected_keys

    def test_join_recorded(self, client, app):
        _register_operator(client)
        invite = client.get("/api/church").json()["invite_code"]
        with TestClient(app) as member:
            member.post("/api/join", json={
                "invite_code": invite, "email": "m@sttest.org",
                "password": "member-good-password"})
        actions = [e["action"] for e in
                   client.get("/api/operator/audit").json()["events"]]
        assert "member_joined" in actions


class TestJobsFeed:

    def test_jobs_feed_cross_church_with_error(self, client):
        _register_operator(client)
        church_id = client.get(
            "/api/operator/churches").json()["churches"][0]["id"]
        _insert_job(church_id, status="done")
        _insert_failed_job(church_id, "boom went the renderer")

        jobs = client.get("/api/operator/jobs").json()["jobs"]
        assert len(jobs) == 2
        failed = [j for j in jobs if j["status"] == "failed"][0]
        assert "boom went the renderer" in failed["error"]
        assert failed["church_name"] == "St. Test Lutheran"
        done = [j for j in jobs if j["status"] == "done"][0]
        assert done["error"] == ""


class TestCacheStats:

    def test_cache_stats_shape_and_by_kind(self, client):
        _register_operator(client)
        _insert_cache("day:2026-7-19")
        _insert_cache("hymn:ELW:504")
        _insert_cache("hymn:ELW:733")
        _insert_cache("passage:John 3:16")

        stats = client.get("/api/operator/cache").json()["cache"]
        assert stats["entries"] == 4
        assert stats["by_kind"] == {"day": 1, "hymn": 2, "passage": 1}
        assert stats["oldest_fetched_at"] is not None
        assert stats["newest_fetched_at"] is not None

    def test_cache_stats_empty(self, client):
        _register_operator(client)
        stats = client.get("/api/operator/cache").json()["cache"]
        assert stats["entries"] == 0
        assert stats["by_kind"] == {}
        assert stats["oldest_fetched_at"] is None
