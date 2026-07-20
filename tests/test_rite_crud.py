"""Tests for the structured rite editor CRUD endpoints (LWS-2).

Covers forking a library rite into a church copy, church scoping, the
library-rite read-only guard, validation of edited blocks, the fork -> edit ->
save -> reload round trip, and version bumps on save.  Uses the same Postgres
test DB and registration helpers as the LWS-1 suite.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from bulletin_maker.core import library as rite_library
from bulletin_maker.web import db, rites as rite_store, security
from bulletin_maker.web.server import create_app

TEST_DATABASE_URL = os.environ.get(
    "BULLETIN_TEST_DATABASE_URL", "postgresql://localhost/bulletin_maker_test")

_TRUNCATE = (
    "TRUNCATE church_texts, rites, rite_modules, churches, users,"
    " past_runs, sessions, auth_tokens, jobs, artifacts, sns_cache,"
    " audit_log RESTART IDENTITY CASCADE"
)

REG = {
    "church_name": "St. Test Lutheran",
    "email": "admin@sttest.org",
    "password": "correct-horse-battery",
    "display_name": "Pat Admin",
}

VOL_PASSWORD = "volunteer-pass"
LIBRARY_RITE_ID = rite_library.SUNDAY_COMMUNION_RITE_ID


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


def _make_second_church():
    church = db.create_church("Second Church", {"church_name": "Second"})
    admin = db.create_user(
        church["id"], "b-admin@second.org",
        security.hash_password("second-admin-pass"), "B Admin", role="admin")
    return church, admin


def _second_client():
    tc = TestClient(create_app())
    tc.post("/api/session", json={
        "email": "b-admin@second.org", "password": "second-admin-pass"})
    return tc


def _fork(client, from_rite_id=LIBRARY_RITE_ID):
    return client.post("/api/rites", json={"from_rite_id": from_rite_id})


# ── Fork ────────────────────────────────────────────────────────────────


class TestFork:

    def test_fork_creates_church_owned_copy(self, client):
        _register(client)
        church_id = db.get_user_by_email(REG["email"])["church_id"]
        resp = _fork(client)
        assert resp.status_code == 200
        rite = resp.json()["rite"]
        assert rite["church_id"] == church_id
        assert rite["id"] != LIBRARY_RITE_ID
        # A bundled library rite is not persisted, so a library fork records no
        # base link (the base_rite_id FK only references stored rites).
        assert rite["base_rite_id"] is None
        assert rite["version"] == 1
        assert rite["name"].startswith("Copy of")
        # Blocks copied verbatim from the source.
        source = rite_library.load_rite(LIBRARY_RITE_ID)
        assert len(rite["blocks"]) == len(source.blocks)

    def test_fork_of_church_rite_records_base_link(self, client):
        _register(client)
        first = _fork(client).json()["rite"]
        second = client.post("/api/rites",
                             json={"from_rite_id": first["id"]}).json()["rite"]
        assert second["base_rite_id"] == first["id"]
        assert second["id"] != first["id"]

    def test_fork_appears_in_listing_and_is_readable(self, client):
        _register(client)
        forked = _fork(client).json()["rite"]
        listed = {r["id"] for r in client.get("/api/rites").json()["rites"]}
        assert forked["id"] in listed
        got = client.get(f"/api/rites/{forked['id']}")
        assert got.status_code == 200
        assert got.json()["rite"]["id"] == forked["id"]

    def test_member_cannot_fork(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = _fork(member)
        assert resp.status_code == 403

    def test_fork_of_unknown_rite_404s(self, client):
        _register(client)
        assert _fork(client, "does_not_exist").status_code == 404


# ── Read scoping ─────────────────────────────────────────────────────────


class TestReadScoping:

    def test_library_rite_is_readable(self, client):
        _register(client)
        resp = client.get(f"/api/rites/{LIBRARY_RITE_ID}")
        assert resp.status_code == 200
        assert resp.json()["rite"]["blocks"]

    def test_other_church_rite_is_forbidden(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        _make_second_church()
        with _second_client() as other:
            resp = other.get(f"/api/rites/{mine['id']}")
        assert resp.status_code == 403

    def test_unknown_rite_404s(self, client):
        _register(client)
        assert client.get("/api/rites/nope").status_code == 404


# ── Update ───────────────────────────────────────────────────────────────


class TestUpdate:

    def test_put_to_library_rite_is_refused(self, client):
        _register(client)
        source = client.get(f"/api/rites/{LIBRARY_RITE_ID}").json()["rite"]
        resp = client.put(f"/api/rites/{LIBRARY_RITE_ID}", json=source)
        assert resp.status_code == 403

    def test_put_other_church_rite_404s(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        _make_second_church()
        with _second_client() as other:
            resp = other.put(f"/api/rites/{mine['id']}", json=mine)
        assert resp.status_code == 404

    def test_member_cannot_update(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.put(f"/api/rites/{mine['id']}", json=mine)
        assert resp.status_code == 403

    def test_invalid_blocks_are_rejected(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        mine["blocks"][0]["type"] = "not_a_real_block_type"
        resp = client.put(f"/api/rites/{mine['id']}", json=mine)
        assert resp.status_code == 422

    def test_dangling_text_ref_rejected_by_validation(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        mine["blocks"].append({
            "id": "bad_ref", "type": "literal_text",
            "text_ref": "elw.does_not_exist"})
        resp = client.put(f"/api/rites/{mine['id']}", json=mine)
        assert resp.status_code == 422
        assert "elw.does_not_exist" in resp.json()["detail"]["error"]

    def test_save_bumps_version(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        assert mine["version"] == 1
        first = client.put(f"/api/rites/{mine['id']}", json=mine).json()["rite"]
        assert first["version"] == 2
        second = client.put(f"/api/rites/{mine['id']}", json=mine).json()["rite"]
        assert second["version"] == 3


# ── Round trip: fork -> edit -> save -> reload ───────────────────────────


class TestRoundTrip:

    def test_reorder_text_and_disable_persist_equal(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]

        # Reorder: swap the first two blocks.
        mine["blocks"][0], mine["blocks"][1] = mine["blocks"][1], mine["blocks"][0]
        # Disable a block via the enabled flag.
        mine["blocks"][2]["enabled"] = False
        # Edit a text-bearing block's text and role labels.
        heading = next(b for b in mine["blocks"] if b["type"] == "heading")
        heading["text"] = "A CUSTOM HEADING"
        mine["meta"]["role_labels"] = {"leader": "L", "congregation": "All"}

        saved = client.put(f"/api/rites/{mine['id']}", json=mine).json()["rite"]
        reloaded = client.get(f"/api/rites/{mine['id']}").json()["rite"]

        # Reloaded equals what was saved (ignoring the version field, which the
        # save bumped) — the edit round-trips losslessly.
        saved_cmp = dict(saved)
        reloaded_cmp = dict(reloaded)
        saved_cmp.pop("version")
        reloaded_cmp.pop("version")
        assert reloaded_cmp == saved_cmp
        assert reloaded["meta"]["role_labels"] == {"leader": "L",
                                                    "congregation": "All"}
        disabled = [b for b in reloaded["blocks"] if b.get("enabled") is False]
        assert len(disabled) == 1
        reloaded_heading = next(
            b for b in reloaded["blocks"] if b["type"] == "heading")
        assert reloaded_heading["text"] == "A CUSTOM HEADING"

    def test_disabled_block_hidden_in_preview(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        target_id = mine["blocks"][0]["id"]
        mine["blocks"][0]["enabled"] = False
        client.put(f"/api/rites/{mine['id']}", json=mine)
        preview = client.post(f"/api/rites/{mine['id']}/preview", json={
            "season": "pentecost", "toggles": {}}).json()
        row = next(b for b in preview["blocks"] if b["id"] == target_id)
        assert row["visible"] is False


# ── Delete ───────────────────────────────────────────────────────────────


class TestDelete:

    def test_admin_can_delete_own(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        resp = client.delete(f"/api/rites/{mine['id']}")
        assert resp.status_code == 200
        assert client.get(f"/api/rites/{mine['id']}").status_code == 404

    def test_cannot_delete_other_church_rite(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        _make_second_church()
        with _second_client() as other:
            resp = other.delete(f"/api/rites/{mine['id']}")
        assert resp.status_code == 404
        assert client.get(f"/api/rites/{mine['id']}").status_code == 200

    def test_delete_library_rite_id_404s(self, client):
        _register(client)
        assert client.delete(f"/api/rites/{LIBRARY_RITE_ID}").status_code == 404

    def test_delete_guarded_when_referenced_by_past_run(self, client):
        _register(client)
        church_id = db.get_user_by_email(REG["email"])["church_id"]
        mine = _fork(client).json()["rite"]
        db.save_past_run(church_id, {"rite_id": mine["id"], "date": "2026-07-19"},
                         {"title": "x"})
        resp = client.delete(f"/api/rites/{mine['id']}")
        assert resp.status_code == 409
        assert client.get(f"/api/rites/{mine['id']}").status_code == 200


# ── Storage helper (fork_rite) ───────────────────────────────────────────


def test_fork_rite_helper_round_trips_blocks():
    church = db.create_church("A", {"church_name": "A"})
    source = rite_library.load_rite(LIBRARY_RITE_ID)
    forked = rite_store.fork_rite(source, church["id"])
    assert forked.church_id == church["id"]
    assert forked.id != source.id
    assert [b.to_dict() for b in forked.blocks] == \
        [b.to_dict() for b in source.blocks]
