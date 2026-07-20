"""Tests for the persistent church text library and rite picker (LWS-1)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from bulletin_maker.core import library as rite_library
from bulletin_maker.core.content_views import build_liturgical_text_options
from bulletin_maker.sns.models import DayContent, Reading
from bulletin_maker.web import church_texts, db, security
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


# ── Storage: CRUD + church-scoping ─────────────────────────────────────


class TestStorage:

    def test_save_and_list(self):
        church = db.create_church("A", {"church_name": "A"})
        saved = church_texts.save_text(
            church["id"], "blessing", "Advent Blessing", "Go in peace.")
        assert saved["kind"] == "blessing"
        assert saved["name"] == "Advent Blessing"
        assert saved["body"] == "Go in peace."

        rows = church_texts.list_texts(church["id"])
        assert len(rows) == 1
        assert rows[0]["id"] == saved["id"]

    def test_list_filters_by_kind(self):
        church = db.create_church("A", {"church_name": "A"})
        church_texts.save_text(church["id"], "blessing", "B1", "x")
        church_texts.save_text(church["id"], "dismissal", "D1", [
            {"role": "P", "text": "Go in peace."},
        ])
        assert len(church_texts.list_texts(church["id"], "blessing")) == 1
        assert len(church_texts.list_texts(church["id"], "dismissal")) == 1
        assert len(church_texts.list_texts(church["id"])) == 2

    def test_resave_same_name_replaces_body(self):
        church = db.create_church("A", {"church_name": "A"})
        first = church_texts.save_text(church["id"], "blessing", "B1", "old")
        second = church_texts.save_text(church["id"], "blessing", "B1", "new")
        assert second["id"] == first["id"]
        assert church_texts.get_text(church["id"], first["id"])["body"] == "new"

    def test_structured_body_round_trips(self):
        church = db.create_church("A", {"church_name": "A"})
        entries = [{"role": "P", "text": "Let us confess."},
                   {"role": "C", "text": "Amen."}]
        saved = church_texts.save_text(church["id"], "confession", "C1", entries)
        assert saved["body"] == entries

    def test_delete_is_church_scoped(self):
        church_a = db.create_church("A", {"church_name": "A"})
        church_b, _ = _make_second_church()
        saved = church_texts.save_text(church_a["id"], "blessing", "B1", "x")
        assert church_texts.delete_text(church_b["id"], saved["id"]) is False
        assert church_texts.get_text(church_a["id"], saved["id"]) is not None
        assert church_texts.delete_text(church_a["id"], saved["id"]) is True
        assert church_texts.get_text(church_a["id"], saved["id"]) is None

    def test_get_is_church_scoped(self):
        church_a = db.create_church("A", {"church_name": "A"})
        church_b, _ = _make_second_church()
        saved = church_texts.save_text(church_a["id"], "blessing", "B1", "x")
        assert church_texts.get_text(church_b["id"], saved["id"]) is None

    def test_texts_by_kind_groups(self):
        church = db.create_church("A", {"church_name": "A"})
        church_texts.save_text(church["id"], "blessing", "B1", "x")
        church_texts.save_text(church["id"], "blessing", "B2", "y")
        church_texts.save_text(church["id"], "dismissal", "D1", [
            {"role": "P", "text": "Go."}])
        grouped = church_texts.texts_by_kind(church["id"])
        assert len(grouped["blessing"]) == 2
        assert len(grouped["dismissal"]) == 1


# ── Endpoint auth + validation ──────────────────────────────────────────


class TestEndpoints:

    def test_admin_can_save_and_list(self, client):
        _register(client)
        resp = client.post("/api/church/texts", json={
            "kind": "blessing", "name": "Advent Blessing", "body": "Go in peace."})
        assert resp.status_code == 200
        assert resp.json()["text"]["name"] == "Advent Blessing"

        listed = client.get("/api/church/texts").json()["texts"]
        assert len(listed) == 1

    def test_member_cannot_save(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.post("/api/church/texts", json={
                "kind": "blessing", "name": "X", "body": "text"})
        assert resp.status_code == 403

    def test_member_can_read(self, client):
        _register(client)
        client.post("/api/church/texts", json={
            "kind": "blessing", "name": "X", "body": "text"})
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.get("/api/church/texts")
        assert resp.status_code == 200
        assert len(resp.json()["texts"]) == 1

    def test_member_cannot_delete(self, client):
        _register(client)
        saved = client.post("/api/church/texts", json={
            "kind": "blessing", "name": "X", "body": "text"}).json()["text"]
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.delete(f"/api/church/texts/{saved['id']}")
        assert resp.status_code == 403

    def test_rejects_unknown_kind(self, client):
        _register(client)
        resp = client.post("/api/church/texts", json={
            "kind": "nope", "name": "X", "body": "text"})
        assert resp.status_code == 422

    def test_rejects_empty_name(self, client):
        _register(client)
        resp = client.post("/api/church/texts", json={
            "kind": "blessing", "name": "  ", "body": "text"})
        assert resp.status_code == 422

    def test_rejects_malformed_structured_body(self, client):
        _register(client)
        resp = client.post("/api/church/texts", json={
            "kind": "confession", "name": "X", "body": "not a list"})
        assert resp.status_code == 422

    def test_cross_church_cannot_read_others(self, client):
        _register(client)
        client.post("/api/church/texts", json={
            "kind": "blessing", "name": "Only Mine", "body": "text"})
        _make_second_church()
        with TestClient(create_app()) as other:
            other.post("/api/session", json={
                "email": "b-admin@second.org", "password": "second-admin-pass"})
            resp = other.get("/api/church/texts")
        assert resp.status_code == 200
        assert resp.json()["texts"] == []

    def test_cross_church_cannot_delete_others(self, client):
        _register(client)
        saved = client.post("/api/church/texts", json={
            "kind": "blessing", "name": "Mine", "body": "text"}).json()["text"]
        _make_second_church()
        with TestClient(create_app()) as other:
            other.post("/api/session", json={
                "email": "b-admin@second.org", "password": "second-admin-pass"})
            resp = other.delete(f"/api/church/texts/{saved['id']}")
        assert resp.status_code == 404
        # Untouched from the owning church's perspective
        assert len(client.get("/api/church/texts").json()["texts"]) == 1

    def test_admin_can_delete_own(self, client):
        _register(client)
        saved = client.post("/api/church/texts", json={
            "kind": "blessing", "name": "Mine", "body": "text"}).json()["text"]
        resp = client.delete(f"/api/church/texts/{saved['id']}")
        assert resp.status_code == 200
        assert client.get("/api/church/texts").json()["texts"] == []

    def test_save_appears_in_next_session(self, client):
        """A saved text is durable across sign-outs, not just the live session."""
        _register(client)
        client.post("/api/church/texts", json={
            "kind": "blessing", "name": "Advent Blessing", "body": "Go in peace."})
        client.delete("/api/session")
        client.post("/api/session", json={
            "email": REG["email"], "password": REG["password"]})
        listed = client.get("/api/church/texts").json()["texts"]
        assert len(listed) == 1
        assert listed[0]["name"] == "Advent Blessing"


# ── Catalog composition ─────────────────────────────────────────────────


class TestCatalog:

    def test_catalog_without_saved_texts_is_unchanged(self):
        day = _day()
        catalog = build_liturgical_text_options(day)
        assert len(catalog["blessing"]["options"]) == 2  # aaronic + sns

    def test_catalog_includes_saved_texts(self):
        day = _day()
        saved = {
            "blessing": [
                {"id": 7, "name": "Advent Blessing", "body": "Go in peace."},
            ],
        }
        catalog = build_liturgical_text_options(day, saved)
        options = catalog["blessing"]["options"]
        assert len(options) == 3
        custom = [o for o in options if o["key"] == "custom:7"][0]
        assert custom["label"] == "Advent Blessing"
        assert custom["data"] == "Go in peace."

    def test_catalog_preserves_defaults_and_existing_shape(self):
        day = _day()
        catalog = build_liturgical_text_options(day, {"blessing": [
            {"id": 1, "name": "X", "body": "y"}]})
        assert catalog["blessing"]["default"] == "aaronic"
        assert catalog["confession"]["type"] == "structured"

    def test_end_to_end_save_then_catalog_via_endpoint(self, client, monkeypatch):
        """The full plumbing: save a text, then /api/day/texts includes it."""
        from unittest.mock import MagicMock

        instance = MagicMock()
        instance.get_day_texts.return_value = _day()
        monkeypatch.setattr(
            "bulletin_maker.web.server.SundaysClient", lambda: instance)

        _register(client)
        client.put("/api/church/sns-link",
                   json={"username": "u", "password": "p"})
        client.post("/api/church/texts", json={
            "kind": "dismissal", "name": "Custom Dismissal",
            "body": [{"role": "P", "text": "Go now."}]})

        client.get("/api/day", params={"date": "2026-07-19", "display": "x"})
        texts = client.get("/api/day/texts").json()["texts"]
        options = texts["dismissal"]["options"]
        custom = [o for o in options if o["label"] == "Custom Dismissal"]
        assert len(custom) == 1
        assert custom[0]["data"] == [{"role": "P", "text": "Go now."}]


# ── Rite listing endpoint ───────────────────────────────────────────────


class TestRitesEndpoint:

    def test_lists_bundled_library_rite(self, client):
        _register(client)
        resp = client.get("/api/rites")
        assert resp.status_code == 200
        rite_ids = {r["id"] for r in resp.json()["rites"]}
        assert rite_library.SUNDAY_COMMUNION_RITE_ID in rite_ids

    def test_requires_login(self, client):
        resp = client.get("/api/rites")
        assert resp.status_code == 401

    def test_includes_church_owned_rite_scoped(self, client):
        from bulletin_maker.core.rite import Rite
        from bulletin_maker.web import rites as rite_store

        _register(client)
        church_id = db.get_user_by_email(REG["email"])["church_id"]
        rite_store.save_rite(Rite(
            id="custom_evening_prayer", name="Evening Prayer",
            church_id=church_id, occasion="evening"))

        resp = client.get("/api/rites").json()
        rite_ids = {r["id"] for r in resp["rites"]}
        assert "custom_evening_prayer" in rite_ids

        _make_second_church()
        with TestClient(create_app()) as other:
            other.post("/api/session", json={
                "email": "b-admin@second.org", "password": "second-admin-pass"})
            other_rites = {r["id"] for r in other.get("/api/rites").json()["rites"]}
        assert "custom_evening_prayer" not in other_rites
        assert rite_library.SUNDAY_COMMUNION_RITE_ID in other_rites

    def test_default_rite_id_unset_renders_bundled_rite(self):
        """ServiceConfig.rite_id=None resolves to the bundled default rite —
        the parity-critical path stays untouched by the picker's plumbing."""
        from bulletin_maker.core.models import ServiceConfig
        from bulletin_maker.renderer.rite_resolver import resolve_bulletin_sequence
        from bulletin_maker.renderer.season import LiturgicalSeason

        config = ServiceConfig(date="2026-7-19", date_display="July 19, 2026")
        sequence = resolve_bulletin_sequence(config, LiturgicalSeason.PENTECOST.value)
        assert sequence  # non-empty — the default rite resolved and rendered
