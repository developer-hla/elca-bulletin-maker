"""Tests for the rite schema, text catalog, storage, and library (LWS-0b).

Fast suite — no PDF rendering.  The storage tests need the same Postgres test
DB the rest of the suite uses (``BULLETIN_TEST_DATABASE_URL``); the schema,
condition-evaluator, catalog, and library tests are pure and need no DB.
"""

from __future__ import annotations

import json
import os

import pytest

from bulletin_maker.core import library
from bulletin_maker.core.rite import (
    Block,
    Condition,
    Rite,
    RiteModule,
    RiteSchemaError,
    RiteValidationError,
    RoleLabels,
    collect_rite_errors,
    condition_applies,
    validate_rite,
)
from bulletin_maker.core.text_catalog import (
    UnknownTextKey,
    get_text,
    has_text,
    text_keys,
)
from bulletin_maker.web import db, rites as rite_store


# ── Schema round-trip ─────────────────────────────────────────────────


def _sample_rite() -> Rite:
    return Rite(
        id="test_rite",
        name="Test Rite",
        tradition="elca",
        occasion="sunday",
        church_id=None,
        role_labels=RoleLabels(leader="P", congregation="C"),
        notes="sample",
        blocks=[
            Block(id="h1", type="heading", data={"text": "GATHERING"}),
            Block(
                id="d1",
                type="dialogue",
                data={
                    "lines": [
                        {"role": "leader", "text": "The Lord be with you."},
                        {"role": "congregation", "text": "And also with you."},
                    ]
                },
            ),
            Block(
                id="creed",
                type="literal_text",
                title="*NICENE CREED",
                condition=Condition(toggles={"creed_nicene": True}),
                data={"text_ref": "elw.nicene_creed", "style": "unison"},
            ),
            Block(
                id="conf",
                type="proper_slot",
                condition=Condition(toggles={"show_confession": True}),
                data={
                    "kind": "confession",
                    "fallback": "elw.confession_form_a",
                },
            ),
            Block(
                id="mod",
                type="module_ref",
                data={"module_id": "some_module"},
            ),
        ],
    )


def test_rite_round_trip_is_identity():
    rite = _sample_rite()
    once = rite.to_dict()
    twice = Rite.from_dict(once).to_dict()
    assert once == twice


def test_block_round_trip_normalizes_payload_order():
    block = Block.from_dict(
        {
            "id": "b",
            "type": "hymn_slot",
            "render": "ref",
            "slot": "gathering",
            "title": "*GATHERING HYMN",
        }
    )
    assert block.to_dict() == {
        "id": "b",
        "type": "hymn_slot",
        "title": "*GATHERING HYMN",
        "slot": "gathering",
        "render": "ref",
    }


def test_condition_round_trip():
    cond = Condition(seasons=["lent"], toggles={"baptism": False}, invert=True)
    assert Condition.from_dict(cond.to_dict()).to_dict() == cond.to_dict()


def test_empty_condition_is_omitted_from_block_dict():
    block = Block(id="b", type="heading", condition=Condition(), data={"text": "X"})
    assert "condition" not in block.to_dict()


def test_role_labels_round_trip():
    labels = RoleLabels(leader="Presider", congregation="Assembly")
    assert RoleLabels.from_dict(labels.to_dict()) == labels


# ── Schema validation failures (fail fast, name the offender) ──────────


def test_unknown_block_type_raises_and_names_type():
    with pytest.raises(RiteSchemaError) as exc:
        Block.from_dict({"id": "x", "type": "not_a_type"})
    assert "not_a_type" in str(exc.value)


def test_unknown_payload_field_raises_and_names_field():
    with pytest.raises(RiteSchemaError) as exc:
        Block.from_dict({"id": "x", "type": "heading", "text": "ok", "bogus": 1})
    assert "bogus" in str(exc.value)


def test_missing_required_field_raises():
    with pytest.raises(RiteSchemaError) as exc:
        Block.from_dict({"id": "x", "type": "heading"})
    assert "text" in str(exc.value)


def test_invalid_enum_value_raises_and_names_field():
    with pytest.raises(RiteSchemaError) as exc:
        Block.from_dict(
            {"id": "x", "type": "hymn_slot", "slot": "nope", "render": "ref"}
        )
    assert "slot" in str(exc.value)


def test_one_of_group_requires_exactly_one():
    with pytest.raises(RiteSchemaError):
        Block.from_dict(
            {"id": "x", "type": "literal_text", "text": "a", "text_ref": "b"}
        )
    with pytest.raises(RiteSchemaError):
        Block.from_dict({"id": "x", "type": "literal_text", "style": "plain"})


def test_dialogue_line_bad_role_raises():
    with pytest.raises(RiteSchemaError) as exc:
        Block.from_dict(
            {
                "id": "x",
                "type": "dialogue",
                "lines": [{"role": "bishop", "text": "hi"}],
            }
        )
    assert "bishop" in str(exc.value)


def test_condition_unknown_field_raises():
    with pytest.raises(RiteSchemaError) as exc:
        Condition.from_dict({"season": ["lent"]})
    assert "season" in str(exc.value)


def test_condition_bad_toggle_value_type_raises():
    with pytest.raises(RiteSchemaError):
        Condition.from_dict({"toggles": {"x": "yes"}})


def test_duplicate_block_id_is_a_validation_error():
    rite = Rite(
        id="r",
        name="R",
        blocks=[
            Block(id="dup", type="heading", data={"text": "A"}),
            Block(id="dup", type="heading", data={"text": "B"}),
        ],
    )
    errors = collect_rite_errors(rite, catalog=frozenset(), modules={})
    assert any("duplicate" in e for e in errors)


# ── Referential validation ─────────────────────────────────────────────


def test_dangling_text_ref_is_an_error():
    rite = Rite(
        id="r",
        name="R",
        blocks=[
            Block(
                id="b",
                type="literal_text",
                data={"text_ref": "elw.does_not_exist", "style": "plain"},
            )
        ],
    )
    with pytest.raises(RiteValidationError) as exc:
        validate_rite(rite)
    assert "elw.does_not_exist" in str(exc.value)


def test_dangling_module_ref_is_an_error():
    rite = Rite(
        id="r",
        name="R",
        blocks=[Block(id="b", type="module_ref", data={"module_id": "missing"})],
    )
    with pytest.raises(RiteValidationError) as exc:
        validate_rite(rite, modules={})
    assert "missing" in str(exc.value)


def test_unknown_profile_ref_is_an_error():
    rite = Rite(
        id="r",
        name="R",
        blocks=[
            Block(id="b", type="literal_text", data={"profile_ref": "not_a_field"})
        ],
    )
    with pytest.raises(RiteValidationError) as exc:
        validate_rite(rite)
    assert "not_a_field" in str(exc.value)


def test_reserved_block_type_is_flagged_by_validation():
    rite = Rite(
        id="r",
        name="R",
        blocks=[Block(id="b", type="announcement_text")],
    )
    errors = collect_rite_errors(rite)
    assert any("reserved" in e for e in errors)


def test_reserved_block_type_parses_but_is_marked_reserved():
    block = Block.from_dict({"id": "b", "type": "prayer_list"})
    assert block.reserved is True


def test_module_block_text_refs_are_validated_through_the_rite():
    module = RiteModule(
        id="m",
        name="M",
        blocks=[
            Block(
                id="mb",
                type="literal_text",
                data={"text_ref": "elw.bogus", "style": "plain"},
            )
        ],
    )
    rite = Rite(
        id="r",
        name="R",
        blocks=[Block(id="ref", type="module_ref", data={"module_id": "m"})],
    )
    with pytest.raises(RiteValidationError) as exc:
        validate_rite(rite, modules={"m": module})
    assert "elw.bogus" in str(exc.value)


# ── Condition evaluator matrix ─────────────────────────────────────────


def test_none_condition_always_applies():
    assert condition_applies(None, {}) is True


def test_empty_condition_always_applies():
    assert condition_applies(Condition(), {"season": "lent"}) is True


def test_season_condition():
    cond = Condition(seasons=["lent", "advent"])
    assert condition_applies(cond, {"season": "lent"}) is True
    assert condition_applies(cond, {"season": "easter"}) is False
    assert condition_applies(cond, {}) is False


def test_feast_condition_uses_intersection():
    cond = Condition(feasts=["christmas_eve", "epiphany"])
    assert condition_applies(cond, {"feasts": ["epiphany"]}) is True
    assert condition_applies(cond, {"feasts": ["pentecost"]}) is False
    assert condition_applies(cond, {}) is False


def test_toggle_condition_true_and_false():
    cond = Condition(toggles={"baptism": True})
    assert condition_applies(cond, {"toggles": {"baptism": True}}) is True
    assert condition_applies(cond, {"toggles": {"baptism": False}}) is False
    assert condition_applies(cond, {}) is False
    off = Condition(toggles={"baptism": False})
    assert condition_applies(off, {"toggles": {"baptism": False}}) is True
    assert condition_applies(off, {}) is True


def test_multiple_toggles_and_together():
    cond = Condition(toggles={"baptism": False, "creed_nicene": True})
    ctx = {"toggles": {"baptism": False, "creed_nicene": True}}
    assert condition_applies(cond, ctx) is True
    ctx_bad = {"toggles": {"baptism": False, "creed_nicene": False}}
    assert condition_applies(cond, ctx_bad) is False


def test_fields_and_together_across_kinds():
    cond = Condition(seasons=["lent"], toggles={"baptism": True})
    assert condition_applies(
        cond, {"season": "lent", "toggles": {"baptism": True}}
    ) is True
    assert condition_applies(
        cond, {"season": "lent", "toggles": {"baptism": False}}
    ) is False
    assert condition_applies(
        cond, {"season": "easter", "toggles": {"baptism": True}}
    ) is False


def test_invert_flips_result():
    cond = Condition(seasons=["lent"], invert=True)
    assert condition_applies(cond, {"season": "lent"}) is False
    assert condition_applies(cond, {"season": "easter"}) is True


# ── Text catalog ───────────────────────────────────────────────────────


def test_get_text_returns_constant():
    from bulletin_maker.renderer.static_text import NICENE_CREED

    assert get_text("elw.nicene_creed") is NICENE_CREED


def test_get_text_unknown_key_fails_fast():
    with pytest.raises(UnknownTextKey):
        get_text("elw.nope")


def test_has_text_and_keys():
    assert has_text("house.invitation_to_communion") is True
    assert has_text("nope") is False
    assert "elw.aaronic_blessing" in text_keys()


def test_catalog_completeness_every_library_ref_resolves():
    """Every text_ref / fallback / text_fallback in the library resolves."""
    from bulletin_maker.core.rite import _text_refs_in_block

    rites, modules = library.load_library()
    refs = set()
    for rite in rites:
        for block in rite.blocks:
            refs.update(_text_refs_in_block(block))
    for module in modules.values():
        for block in module.blocks:
            refs.update(_text_refs_in_block(block))
    assert refs, "expected the library to reference at least one text key"
    for key in refs:
        assert has_text(key), "unresolved text key %r" % key
        get_text(key)


# ── Library rite loads and validates ───────────────────────────────────


def test_library_validates_at_import():
    library.validate_library()


def test_library_rite_round_trips_against_its_json():
    raw = json.loads(
        (library.LIBRARY_DIR / "elw_sunday_communion.json").read_text()
    )
    rite = library.load_rite(library.SUNDAY_COMMUNION_RITE_ID)
    assert rite.to_dict() == raw


def test_library_module_round_trips_against_its_json():
    raw = json.loads(
        (library.LIBRARY_DIR / "elw_holy_baptism.json").read_text()
    )
    module = library.load_modules()[library.HOLY_BAPTISM_MODULE_ID]
    assert module.to_dict() == raw


def test_library_baptism_module_ref_resolves():
    rite = library.load_rite(library.SUNDAY_COMMUNION_RITE_ID)
    modules = library.load_modules()
    module_ids = {
        b.data["module_id"] for b in rite.blocks if b.type == "module_ref"
    }
    assert module_ids <= set(modules)
    assert library.HOLY_BAPTISM_MODULE_ID in module_ids


# ── Storage round-trip + version bump (needs the test DB) ──────────────

TEST_DATABASE_URL = os.environ.get(
    "BULLETIN_TEST_DATABASE_URL", "postgresql://localhost/bulletin_maker_test"
)

_TRUNCATE = "TRUNCATE rites, rite_modules, churches RESTART IDENTITY CASCADE"


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    db.reset_for_tests()
    with db.connect() as conn:
        conn.execute(_TRUNCATE)


def test_storage_round_trip_preserves_dict():
    rite = _sample_rite()
    # module_ref block validation is referential, not structural; storage does
    # not validate, so a self-contained round-trip rite is fine.
    saved = rite_store.save_rite(rite)
    assert saved.version == 1
    loaded = rite_store.get_rite(rite.id)
    assert loaded is not None
    assert loaded.to_dict() == rite.to_dict()


def test_storage_bumps_version_on_resave():
    rite = _sample_rite()
    rite_store.save_rite(rite)
    again = rite_store.save_rite(rite)
    assert again.version == 2
    third = rite_store.save_rite(rite)
    assert third.version == 3


def test_get_rite_missing_returns_none():
    assert rite_store.get_rite("nope") is None


def test_list_rites_includes_library_and_church():
    library_rite = Rite(id="lib", name="Lib", church_id=None, occasion="sunday")
    church = db.create_church("Test Church", {"name": "Test Church"})
    church_rite = Rite(
        id="own", name="Own", church_id=church["id"], occasion="sunday"
    )
    other = db.create_church("Other Church", {"name": "Other Church"})
    other_rite = Rite(
        id="other", name="Other", church_id=other["id"], occasion="sunday"
    )
    rite_store.save_rite(library_rite)
    rite_store.save_rite(church_rite)
    rite_store.save_rite(other_rite)

    ids = [r.id for r in rite_store.list_rites(church["id"])]
    assert "lib" in ids
    assert "own" in ids
    assert "other" not in ids


def test_module_storage_round_trip_and_version_bump():
    module = RiteModule(
        id="m",
        name="M",
        blocks=[Block(id="h", type="heading", data={"text": "HI"})],
    )
    saved = rite_store.save_module(module)
    assert saved.version == 1
    loaded = rite_store.get_module("m")
    assert loaded is not None
    assert loaded.to_dict() == module.to_dict()
    again = rite_store.save_module(module)
    assert again.version == 2


def test_library_rite_persists_and_reloads_identically():
    rite = library.load_rite(library.SUNDAY_COMMUNION_RITE_ID)
    for module in library.load_modules().values():
        rite_store.save_module(module)
    rite_store.save_rite(rite)
    loaded = rite_store.get_rite(rite.id)
    assert loaded is not None
    assert loaded.to_dict() == rite.to_dict()
