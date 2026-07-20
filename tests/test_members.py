"""Tests for the church-admin Members panel (WS-6)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from bulletin_maker.web import db, email, security
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

VOL_PASSWORD = "volunteer-pass"


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


def _invite_code(client):
    return client.get("/api/church").json()["invite_code"]


def _join(client, invite_code, email_addr, name="Vol"):
    return client.post("/api/join", json={
        "invite_code": invite_code, "email": email_addr,
        "password": VOL_PASSWORD, "display_name": name})


def _login(client, email_addr, password):
    return client.post("/api/session",
                       json={"email": email_addr, "password": password})


def _make_second_church():
    church = db.create_church("Second Church", {"church_name": "Second"})
    admin = db.create_user(
        church["id"], "b-admin@second.org",
        security.hash_password("second-admin-pass"), "B Admin", role="admin")
    return church, admin


class TestMemberList:

    def test_lists_own_church_only(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            assert _join(member, code, "vol@sttest.org").status_code == 200
        _make_second_church()
        resp = client.get("/api/church/members")
        assert resp.status_code == 200
        emails = {row["email"] for row in resp.json()["members"]}
        assert emails == {"admin@sttest.org", "vol@sttest.org"}

    def test_marks_current_user(self, client):
        _register(client)
        roster = client.get("/api/church/members").json()["members"]
        me = [m for m in roster if m["email"] == REG["email"]][0]
        assert me["is_you"] is True
        assert me["role"] == "admin"

    def test_member_cannot_list(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.get("/api/church/members")
        assert resp.status_code == 403


class TestRemoveMember:

    def test_scoping_cannot_remove_other_church(self, client):
        _register(client)
        _church_b, admin_b = _make_second_church()
        resp = client.delete("/api/church/members/" + str(admin_b["id"]))
        assert resp.status_code == 404

    def test_remove_self_refused(self, client):
        _register(client)
        me = db.get_user_by_email(REG["email"])
        # add a co-admin so the last-admin guard passes and the self-guard
        # is the reason for refusal
        db.create_user(me["church_id"], "co-admin@sttest.org",
                       security.hash_password("co-admin-pass"), "Co",
                       role="admin")
        resp = client.delete("/api/church/members/" + str(me["id"]))
        assert resp.status_code == 422
        assert "yourself" in resp.json()["detail"]["error"]

    def test_last_admin_refused(self, client):
        _register(client)
        me = db.get_user_by_email(REG["email"])
        resp = client.delete("/api/church/members/" + str(me["id"]))
        assert resp.status_code == 422
        assert "last admin" in resp.json()["detail"]["error"]

    def test_can_remove_co_admin(self, client):
        _register(client)
        me = db.get_user_by_email(REG["email"])
        co = db.create_user(me["church_id"], "co-admin@sttest.org",
                            security.hash_password("co-admin-pass"), "Co",
                            role="admin")
        resp = client.delete("/api/church/members/" + str(co["id"]))
        assert resp.status_code == 200
        assert db.get_user(co["id"]) is None

    def test_removed_user_session_invalidated(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            assert _join(member, code, "vol@sttest.org").status_code == 200
            assert member.get("/api/session").json()["authenticated"] is True
            vol = db.get_user_by_email("vol@sttest.org")
            assert client.delete(
                "/api/church/members/" + str(vol["id"])).status_code == 200
            assert member.get("/api/session").json()["authenticated"] is False

    def test_remove_nulls_owned_jobs(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
        vol = db.get_user_by_email("vol@sttest.org")
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id, church_id, user_id) VALUES (%s, %s, %s)",
                ("job-vol-1", vol["church_id"], vol["id"]))
        assert client.delete(
            "/api/church/members/" + str(vol["id"])).status_code == 200
        with db.connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM jobs WHERE id = %s",
                ("job-vol-1",)).fetchone()
        assert row["user_id"] is None


class TestInviteEmail:

    def test_send_invite_captures_email(self, client):
        _register(client)
        code = _invite_code(client)
        email.sent_for_tests.clear()
        resp = client.post("/api/church/invite/send",
                           json={"email": "newvol@sttest.org"})
        assert resp.status_code == 200
        assert len(email.sent_for_tests) == 1
        msg = email.sent_for_tests[0]
        assert msg["to"] == "newvol@sttest.org"
        assert code in msg["text"]

    def test_send_invite_uses_app_base_url(self, client, monkeypatch):
        monkeypatch.setenv("APP_BASE_URL", "https://bulletins.example.org")
        _register(client)
        email.sent_for_tests.clear()
        client.post("/api/church/invite/send",
                    json={"email": "newvol@sttest.org"})
        assert "https://bulletins.example.org/#join=" \
            in email.sent_for_tests[-1]["text"]

    def test_send_invite_rejects_bad_email(self, client):
        _register(client)
        resp = client.post("/api/church/invite/send", json={"email": "nope"})
        assert resp.status_code == 422

    def test_member_cannot_send_invite(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.post("/api/church/invite/send",
                               json={"email": "x@sttest.org"})
        assert resp.status_code == 403


class TestRegenerateInvite:

    def test_regenerate_invalidates_old_code(self, client):
        _register(client)
        old_code = _invite_code(client)
        resp = client.post("/api/church/invite/regenerate")
        assert resp.status_code == 200
        new_code = resp.json()["invite_code"]
        assert new_code != old_code
        with TestClient(create_app()) as joiner:
            old = _join(joiner, old_code, "old@sttest.org")
            assert old.status_code == 403
            new = _join(joiner, new_code, "new@sttest.org")
            assert new.status_code == 200

    def test_member_cannot_regenerate(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.post("/api/church/invite/regenerate")
        assert resp.status_code == 403


class TestUsage:

    def test_counts_generations_and_members(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
        church_id = db.get_user_by_email(REG["email"])["church_id"]
        with db.connect() as conn:
            for i in range(3):
                conn.execute(
                    "INSERT INTO jobs (id, church_id) VALUES (%s, %s)",
                    (f"job-{i}", church_id))
        resp = client.get("/api/church/usage")
        assert resp.status_code == 200
        body = resp.json()
        assert body["generates_this_month"] == 3
        assert body["member_count"] == 2

    def test_usage_is_church_scoped(self, client):
        _register(client)
        church_b, _admin_b = _make_second_church()
        with db.connect() as conn:
            for i in range(5):
                conn.execute(
                    "INSERT INTO jobs (id, church_id) VALUES (%s, %s)",
                    (f"job-b-{i}", church_b["id"]))
        body = client.get("/api/church/usage").json()
        assert body["generates_this_month"] == 0
        assert body["member_count"] == 1

    def test_member_cannot_view_usage(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.get("/api/church/usage")
        assert resp.status_code == 403
