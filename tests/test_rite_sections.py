"""Per-section fill / save / reuse for canonical_slot occasion sections.

Covers the storage helper (``section_overrides``), the override winning at
resolution (proving the generate-path wiring), and the three section endpoints
(status computation + save/delete round-trip).  All S&S interaction is mocked —
no real liturgy is read.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Warm the renderer package first (cold-import cycle) before rite_resolver.
import bulletin_maker.renderer  # noqa: F401
from bulletin_maker.core.content_source import ContentContext
from bulletin_maker.core.rite import Block, Rite
from bulletin_maker.renderer.rite_resolver import resolve_canonical_slot
from bulletin_maker.web import church_texts, db, rites as rite_store, security
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

FUNERAL_RITE_ID = "elw_funeral"
OCCASION_KIND = church_texts.OCCASION_SECTION_KIND


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


# ── Storage: section_overrides helper ──────────────────────────────────


class TestSectionOverrides:

    def test_returns_section_key_to_text(self):
        church = db.create_church("A", {"church_name": "A"})
        church_texts.save_text(
            church["id"], OCCASION_KIND, "funeral_greeting", "Grace to you.")
        church_texts.save_text(
            church["id"], OCCASION_KIND, "marriage_vows", "I take you.")
        # A non-occasion kind must never leak into the section dict.
        church_texts.save_text(church["id"], "blessing", "B", "unrelated")

        overrides = church_texts.section_overrides(church["id"])
        assert overrides == {
            "funeral_greeting": "Grace to you.",
            "marriage_vows": "I take you.",
        }

    def test_empty_without_saved_sections(self):
        church = db.create_church("A", {"church_name": "A"})
        assert church_texts.section_overrides(church["id"]) == {}

    def test_scoped_per_church(self):
        church_a = db.create_church("A", {"church_name": "A"})
        church_b, _ = _make_second_church()
        church_texts.save_text(
            church_a["id"], OCCASION_KIND, "funeral_greeting", "A wording")
        assert church_texts.section_overrides(church_b["id"]) == {}


# ── Resolution: a saved override wins (the generate-path payload) ────────


class TestOverrideWinsAtResolution:

    def _greeting_block(self):
        return Block(id="greeting", type="canonical_slot",
                     data={"section_key": "funeral_greeting"})

    def test_saved_override_beats_the_sns_fill(self, monkeypatch):
        import bulletin_maker.renderer.rite_resolver as rr
        monkeypatch.setattr(rr, "fill_section", lambda key, ctx: "SNS WORDING")

        church = db.create_church("A", {"church_name": "A"})
        church_texts.save_text(
            church["id"], OCCASION_KIND, "funeral_greeting", "Church greeting.")
        overrides = church_texts.section_overrides(church["id"])
        context = ContentContext(church_texts=overrides)

        assert resolve_canonical_slot(self._greeting_block(), context) \
            == "Church greeting."

    def test_without_override_falls_through_to_fill(self, monkeypatch):
        import bulletin_maker.renderer.rite_resolver as rr
        monkeypatch.setattr(rr, "fill_section", lambda key, ctx: "SNS WORDING")

        church = db.create_church("A", {"church_name": "A"})
        context = ContentContext(
            church_texts=church_texts.section_overrides(church["id"]))

        assert resolve_canonical_slot(self._greeting_block(), context) \
            == "SNS WORDING"


# ── Endpoints: status + save/delete ─────────────────────────────────────


class TestSectionEndpoints:

    def test_status_needs_fill_when_unentitled(self, client):
        """No S&S link → every mapped section degrades to needs_fill."""
        _register(client)
        resp = client.get(f"/api/rites/{FUNERAL_RITE_ID}/sections")
        assert resp.status_code == 200
        sections = resp.json()["sections"]
        keys = {s["section_key"] for s in sections}
        assert "funeral_greeting" in keys
        for s in sections:
            assert s["status"] == "needs_fill"
            assert s["has_override"] is False
            assert s["override_text"] is None

    def test_status_s_and_s_when_fill_returns_text(self, client, monkeypatch):
        monkeypatch.setattr(
            "bulletin_maker.web.server.fill_section",
            lambda key, ctx: "PULLED" if key == "funeral_greeting" else None)
        _register(client)
        sections = client.get(
            f"/api/rites/{FUNERAL_RITE_ID}/sections").json()["sections"]
        by_key = {s["section_key"]: s for s in sections}
        assert by_key["funeral_greeting"]["status"] == "s_and_s"
        assert by_key["funeral_commendation"]["status"] == "needs_fill"

    def test_status_custom_after_save(self, client):
        _register(client)
        saved = client.post(
            f"/api/rites/{FUNERAL_RITE_ID}/sections/funeral_greeting",
            json={"text": "Our greeting."})
        assert saved.status_code == 200
        sections = client.get(
            f"/api/rites/{FUNERAL_RITE_ID}/sections").json()["sections"]
        by_key = {s["section_key"]: s for s in sections}
        greeting = by_key["funeral_greeting"]
        assert greeting["status"] == "custom"
        assert greeting["has_override"] is True
        assert greeting["override_text"] == "Our greeting."

    def test_status_unmapped_for_unknown_section_key(self, client):
        _register(client)
        church_id = db.get_user_by_email(REG["email"])["church_id"]
        rite = Rite(
            id="custom_rite", name="Custom", church_id=church_id,
            occasion="funeral",
            blocks=[Block(id="x", type="canonical_slot",
                          data={"section_key": "made_up_section"})])
        rite_store.save_rite(rite)
        sections = client.get(
            "/api/rites/custom_rite/sections").json()["sections"]
        assert sections[0]["status"] == "unmapped"

    def test_save_persists_as_occasion_section(self, client):
        _register(client)
        client.post(f"/api/rites/{FUNERAL_RITE_ID}/sections/funeral_greeting",
                    json={"text": "Grace to you."})
        listed = client.get(
            "/api/church/texts?kind=occasion_section").json()["texts"]
        assert len(listed) == 1
        assert listed[0]["name"] == "funeral_greeting"
        assert listed[0]["body"] == "Grace to you."

    def test_save_then_delete_round_trip(self, client):
        _register(client)
        client.post(f"/api/rites/{FUNERAL_RITE_ID}/sections/funeral_greeting",
                    json={"text": "Grace to you."})
        deleted = client.delete(
            f"/api/rites/{FUNERAL_RITE_ID}/sections/funeral_greeting")
        assert deleted.status_code == 200
        after = client.get(
            "/api/church/texts?kind=occasion_section").json()["texts"]
        assert after == []

    def test_resave_updates_same_row(self, client):
        _register(client)
        client.post(f"/api/rites/{FUNERAL_RITE_ID}/sections/funeral_greeting",
                    json={"text": "First."})
        client.post(f"/api/rites/{FUNERAL_RITE_ID}/sections/funeral_greeting",
                    json={"text": "Second."})
        listed = client.get(
            "/api/church/texts?kind=occasion_section").json()["texts"]
        assert len(listed) == 1
        assert listed[0]["body"] == "Second."

    def test_member_cannot_save(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.post(
                f"/api/rites/{FUNERAL_RITE_ID}/sections/funeral_greeting",
                json={"text": "x"})
        assert resp.status_code == 403

    def test_member_can_read_status(self, client):
        _register(client)
        code = _invite_code(client)
        with TestClient(create_app()) as member:
            _join(member, code, "vol@sttest.org")
            resp = member.get(f"/api/rites/{FUNERAL_RITE_ID}/sections")
        assert resp.status_code == 200

    def test_save_rejects_section_not_in_rite(self, client):
        _register(client)
        resp = client.post(
            f"/api/rites/{FUNERAL_RITE_ID}/sections/not_in_this_rite",
            json={"text": "x"})
        assert resp.status_code == 404

    def test_save_rejects_empty_text(self, client):
        _register(client)
        resp = client.post(
            f"/api/rites/{FUNERAL_RITE_ID}/sections/funeral_greeting",
            json={"text": "   "})
        assert resp.status_code == 422

    def test_delete_without_saved_override_404(self, client):
        _register(client)
        resp = client.delete(
            f"/api/rites/{FUNERAL_RITE_ID}/sections/funeral_greeting")
        assert resp.status_code == 404

    def test_cross_church_cannot_save_to_others_rite(self, client):
        """A church-owned rite is never writable by another church."""
        _register(client)
        church_id = db.get_user_by_email(REG["email"])["church_id"]
        rite = Rite(
            id="a_owned_rite", name="Owned", church_id=church_id,
            occasion="funeral",
            blocks=[Block(id="g", type="canonical_slot",
                          data={"section_key": "funeral_greeting"})])
        rite_store.save_rite(rite)
        _make_second_church()
        with TestClient(create_app()) as other:
            other.post("/api/session", json={
                "email": "b-admin@second.org", "password": "second-admin-pass"})
            resp = other.post(
                "/api/rites/a_owned_rite/sections/funeral_greeting",
                json={"text": "x"})
        assert resp.status_code == 403
