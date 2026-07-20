"""Tests for rite export/import (LWS-3): portability to and from a JSON file.

Covers: export returns the rite's to_dict() shape with an attachment header
and is church-scoped (own rites AND library rites are exportable, another
church's private rite is not); import validates structurally and
referentially before ever storing anything; import always creates a fresh
church-scoped row (never overwrites, never claims another church's id); the
export -> import round trip preserves blocks; and importing a library rite's
exported file creates that importing church's own copy.

Uses the same Postgres test DB and registration helpers as the LWS-2 suite.
"""

from __future__ import annotations

import io
import json
import os

import pytest
from fastapi.testclient import TestClient

from bulletin_maker.core import library as rite_library
from bulletin_maker.web import db, rites as rite_store, security
from bulletin_maker.web.server import create_app

TEST_DATABASE_URL = os.environ.get(
    "BULLETIN_TEST_DATABASE_URL",
    "postgresql://localhost/bulletin_maker_test_export")

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


def _upload(client, payload):
    data = json.dumps(payload).encode("utf-8")
    return client.post(
        "/api/rites/import",
        files={"file": ("rite.json", io.BytesIO(data), "application/json")})


# ── Export ─────────────────────────────────────────────────────────────


class TestExport:

    def test_export_own_rite_returns_to_dict_shape(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        resp = client.get(f"/api/rites/{mine['id']}/export")
        assert resp.status_code == 200
        assert resp.json() == mine
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.headers["content-disposition"].endswith('.json"')

    def test_export_filename_is_a_slug_of_the_name(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        update = dict(mine)
        update["name"] = "My Church's Special Rite!"
        client.put(f"/api/rites/{mine['id']}", json=update)
        resp = client.get(f"/api/rites/{mine['id']}/export")
        disposition = resp.headers["content-disposition"]
        assert "my-church-s-special-rite" in disposition

    def test_export_library_rite_is_allowed(self, client):
        _register(client)
        resp = client.get(f"/api/rites/{LIBRARY_RITE_ID}/export")
        assert resp.status_code == 200
        source = rite_library.load_rite(LIBRARY_RITE_ID)
        assert resp.json() == source.to_dict()

    def test_cannot_export_other_churchs_private_rite(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        _make_second_church()
        with _second_client() as other:
            resp = other.get(f"/api/rites/{mine['id']}/export")
        assert resp.status_code == 403

    def test_export_unknown_rite_404s(self, client):
        _register(client)
        assert client.get("/api/rites/does_not_exist/export").status_code == 404

    def test_member_can_export(self, client):
        # Export is a read, gated like the existing GET — any church user.
        _register(client)
        mine = _fork(client).json()["rite"]
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.get(f"/api/rites/{mine['id']}/export")
        assert resp.status_code == 200


# ── Import: validation ───────────────────────────────────────────────────


class TestImportValidation:

    def test_import_rejects_invalid_json_and_stores_nothing(self, client):
        _register(client)
        before = {r["id"] for r in client.get("/api/rites").json()["rites"]}
        resp = client.post(
            "/api/rites/import",
            files={"file": ("rite.json", io.BytesIO(b"not json"),
                            "application/json")})
        assert resp.status_code == 422
        assert "JSON" in resp.json()["detail"]["error"]
        after = {r["id"] for r in client.get("/api/rites").json()["rites"]}
        assert after == before

    def test_import_rejects_non_object_json(self, client):
        _register(client)
        resp = client.post(
            "/api/rites/import",
            files={"file": ("rite.json", io.BytesIO(b"[1, 2, 3]"),
                            "application/json")})
        assert resp.status_code == 422

    def test_import_rejects_bad_block_type_and_stores_nothing(self, client):
        _register(client)
        source = rite_library.load_rite(LIBRARY_RITE_ID).to_dict()
        source["blocks"][0]["type"] = "not_a_real_block_type"
        before = {r["id"] for r in client.get("/api/rites").json()["rites"]}
        resp = _upload(client, source)
        assert resp.status_code == 422
        assert "not_a_real_block_type" in resp.json()["detail"]["error"]
        after = {r["id"] for r in client.get("/api/rites").json()["rites"]}
        assert after == before

    def test_import_rejects_dangling_text_ref(self, client):
        _register(client)
        source = rite_library.load_rite(LIBRARY_RITE_ID).to_dict()
        source["blocks"].append({
            "id": "bad_ref", "type": "literal_text",
            "text_ref": "elw.does_not_exist"})
        resp = _upload(client, source)
        assert resp.status_code == 422
        assert "elw.does_not_exist" in resp.json()["detail"]["error"]

    def test_member_cannot_import(self, client):
        _register(client)
        code = _invite_code(client)
        source = rite_library.load_rite(LIBRARY_RITE_ID).to_dict()
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = _upload(member, source)
        assert resp.status_code == 403

    def test_import_accepts_raw_json_body_not_just_multipart(self, client):
        _register(client)
        source = rite_library.load_rite(LIBRARY_RITE_ID).to_dict()
        resp = client.post("/api/rites/import", json=source)
        assert resp.status_code == 200


# ── Import: ownership / scoping ──────────────────────────────────────────


class TestImportOwnership:

    def test_import_creates_church_scoped_rite_with_fresh_id(self, client):
        _register(client)
        church_id = db.get_user_by_email(REG["email"])["church_id"]
        source = rite_library.load_rite(LIBRARY_RITE_ID).to_dict()
        resp = _upload(client, source)
        assert resp.status_code == 200
        imported = resp.json()["rite"]
        assert imported["church_id"] == church_id
        assert imported["id"] != source["id"]
        assert imported["version"] == 1
        assert imported["base_rite_id"] is None

    def test_import_never_overwrites_an_existing_rite(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        # Feed the exported file of an *existing* rite back through import —
        # it must create a new row, not update the existing one in place.
        exported = client.get(f"/api/rites/{mine['id']}/export").json()
        resp = _upload(client, exported)
        assert resp.status_code == 200
        imported = resp.json()["rite"]
        assert imported["id"] != mine["id"]
        # The original is untouched.
        still_there = client.get(f"/api/rites/{mine['id']}").json()["rite"]
        assert still_there == mine

    def test_import_cannot_claim_another_churchs_id_or_ownership(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        exported = client.get(f"/api/rites/{mine['id']}/export").json()
        _make_second_church()
        with _second_client() as other:
            resp = _upload(other, exported)
        assert resp.status_code == 200
        imported = resp.json()["rite"]
        second_church_id = db.get_user_by_email("b-admin@second.org")["church_id"]
        assert imported["church_id"] == second_church_id
        assert imported["id"] != mine["id"]
        # The first church's rite is untouched and still theirs alone.
        mine_reloaded = client.get(f"/api/rites/{mine['id']}").json()["rite"]
        assert mine_reloaded["church_id"] != second_church_id

    def test_name_collision_gets_imported_suffix(self, client):
        _register(client)
        mine = _fork(client, from_rite_id=LIBRARY_RITE_ID).json()["rite"]
        exported = client.get(f"/api/rites/{mine['id']}/export").json()
        resp = _upload(client, exported)
        assert resp.status_code == 200
        imported = resp.json()["rite"]
        assert imported["name"] == mine["name"] + " (imported)"
        assert imported["id"] != mine["id"]

    def test_no_collision_keeps_original_name(self, client):
        _register(client)
        source = rite_library.load_rite(LIBRARY_RITE_ID).to_dict()
        source["name"] = "A Totally Unused Name"
        resp = _upload(client, source)
        assert resp.status_code == 200
        assert resp.json()["rite"]["name"] == "A Totally Unused Name"


# ── Round trip: export -> import -> blocks equal ─────────────────────────


class TestRoundTrip:

    def test_export_then_import_blocks_equal_original(self, client):
        _register(client)
        mine = _fork(client).json()["rite"]
        exported = client.get(f"/api/rites/{mine['id']}/export").json()
        imported = _upload(client, exported).json()["rite"]
        assert imported["blocks"] == mine["blocks"]
        assert imported["meta"]["role_labels"] == mine["meta"]["role_labels"]

    def test_import_of_library_rite_file_creates_churchs_own_copy(self, client):
        _register(client)
        church_id = db.get_user_by_email(REG["email"])["church_id"]
        export_resp = client.get(f"/api/rites/{LIBRARY_RITE_ID}/export")
        assert export_resp.status_code == 200
        source = rite_library.load_rite(LIBRARY_RITE_ID)
        imported = _upload(client, export_resp.json()).json()["rite"]
        assert imported["church_id"] == church_id
        assert imported["id"] != LIBRARY_RITE_ID
        assert imported["blocks"] == [b.to_dict() for b in source.blocks]
        # Persisted for real — readable back via the normal GET.
        reloaded = client.get(f"/api/rites/{imported['id']}").json()["rite"]
        assert reloaded == imported


# ── Storage helpers (prepare_import / import_name_collides) ──────────────


def test_prepare_import_helper_resets_ownership_and_round_trips_blocks():
    church = db.create_church("A", {"church_name": "A"})
    source = rite_library.load_rite(LIBRARY_RITE_ID)
    imported = rite_store.prepare_import(source.to_dict(), church["id"])
    assert imported.church_id == church["id"]
    assert imported.id != source.id
    assert imported.version == 1
    assert imported.base_rite_id is None
    assert [b.to_dict() for b in imported.blocks] == \
        [b.to_dict() for b in source.blocks]


def test_import_name_collides_helper():
    church = db.create_church("A", {"church_name": "A"})
    source = rite_library.load_rite(LIBRARY_RITE_ID)
    forked = rite_store.fork_rite(source, church["id"], name="Sunday Communion")
    rite_store.save_rite(forked)
    assert rite_store.import_name_collides(
        "Sunday Communion", forked.occasion, church["id"])
    assert not rite_store.import_name_collides(
        "Some Other Name", forked.occasion, church["id"])
