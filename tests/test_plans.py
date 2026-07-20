"""Tests for plan limit enforcement (WS-8)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from bulletin_maker.web import db, plans, security
from bulletin_maker.web.server import create_app

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
        conn.execute("UPDATE plans SET limits_jsonb = '{}' WHERE plan = 'free'")
    monkeypatch.setattr(security, "KEYFILE", tmp_path / "secret.key")
    monkeypatch.delenv("BULLETIN_SECRET_KEY", raising=False)
    monkeypatch.delenv("BULLETIN_REGISTRATION_CODE", raising=False)
    monkeypatch.delenv("BULLETIN_HOSTED", raising=False)


@pytest.fixture()
def client():
    with TestClient(create_app()) as tc:
        yield tc


def _set_free_limits(limits: dict) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE plans SET limits_jsonb = %s WHERE plan = 'free'",
            (Jsonb(limits),))


def _make_church() -> dict:
    return db.create_church("St. Test Lutheran", {"church_name": "St. Test"})


def _insert_jobs(church_id: int, count: int) -> None:
    with db.connect() as conn:
        for i in range(count):
            conn.execute(
                "INSERT INTO jobs (id, church_id) VALUES (%s, %s)",
                (f"job-{church_id}-{i}", church_id))


class TestFreePlanUnlimited:

    def test_check_limit_noop_for_both_actions(self):
        church = _make_church()
        _insert_jobs(church["id"], 25)
        db.create_user(church["id"], "a@b.org", "h", "A")
        db.create_user(church["id"], "c@d.org", "h", "C")
        # Free plan sets no limits — neither gate raises.
        plans.check_limit(church, "generate")
        plans.check_limit(church, "join")

    def test_join_endpoint_unlimited_on_free_plan(self, client):
        assert client.post("/api/register", json=REG).status_code == 200
        invite = client.get("/api/church").json()["invite_code"]
        client.delete("/api/session")
        resp = client.post("/api/join", json={
            "invite_code": invite, "email": "vol@sttest.org",
            "password": "volunteer-pass", "display_name": "Vi"})
        assert resp.status_code == 200


class TestMaxUsersLimit:

    def test_check_limit_raises_at_capacity(self):
        church = _make_church()
        _set_free_limits({"max_users": 1})
        db.create_user(church["id"], "a@b.org", "h", "A")
        with pytest.raises(plans.PlanLimitError):
            plans.check_limit(church, "join")

    def test_check_limit_ok_under_capacity(self):
        church = _make_church()
        _set_free_limits({"max_users": 3})
        db.create_user(church["id"], "a@b.org", "h", "A")
        plans.check_limit(church, "join")

    def test_join_endpoint_returns_403_plan_limit(self, client):
        assert client.post("/api/register", json=REG).status_code == 200
        invite = client.get("/api/church").json()["invite_code"]
        _set_free_limits({"max_users": 1})  # admin already fills the seat
        client.delete("/api/session")
        resp = client.post("/api/join", json={
            "invite_code": invite, "email": "vol@sttest.org",
            "password": "volunteer-pass", "display_name": "Vi"})
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["error_type"] == "plan_limit"
        assert "member limit" in detail["error"]


class TestGeneratesPerMonthLimit:

    def test_check_limit_raises_at_capacity(self):
        church = _make_church()
        _set_free_limits({"generates_per_month": 2})
        _insert_jobs(church["id"], 2)
        with pytest.raises(plans.PlanLimitError):
            plans.check_limit(church, "generate")

    def test_check_limit_ok_under_capacity(self):
        church = _make_church()
        _set_free_limits({"generates_per_month": 5})
        _insert_jobs(church["id"], 2)
        plans.check_limit(church, "generate")

    def test_count_is_church_scoped(self):
        church = _make_church()
        other = db.create_church("Other", {"church_name": "Other"})
        _set_free_limits({"generates_per_month": 1})
        _insert_jobs(other["id"], 5)
        plans.check_limit(church, "generate")


class TestUnknownAction:

    def test_unknown_action_raises_value_error(self):
        church = _make_church()
        with pytest.raises(ValueError):
            plans.check_limit(church, "teleport")
