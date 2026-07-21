"""Tests for the ELW Funeral and Marriage library rites (skeleton layer).

Fast, DB-free.  Both rites are authored as the always-works SKELETON: they fix
the ordo structure, chrome, public-domain reading/psalm slots, the public-domain
traditional Lord's Prayer, and per-service variables, while every canonical
(copyrighted) section is an empty keyed ``canonical_slot`` resolved through
``content_source``.  These tests assert structural facts — each rite loads,
validates referentially, round-trips against its JSON, every text/module ref
resolves, the declared variables match, the section_key set is exactly as
expected, and canonical_slot resolution returns the entitlement placeholder with
no church text and the saved custom text when present.  No liturgical prose is
asserted (none is bundled).
"""

from __future__ import annotations

import json

import pytest

import bulletin_maker.renderer  # noqa: F401  (warm the cold-import cycle)
from bulletin_maker.core import library
from bulletin_maker.core.content_source import (
    ENTITLEMENT_PLACEHOLDER,
    ContentContext,
)
from bulletin_maker.core.rite import _text_refs_in_block, validate_rite
from bulletin_maker.core.text_catalog import get_text, has_text
from bulletin_maker.renderer.rite_resolver import resolve_canonical_slot

RITE_IDS = (library.FUNERAL_RITE_ID, library.MARRIAGE_RITE_ID)

EXPECTED_OCCASION = {
    library.FUNERAL_RITE_ID: "funeral",
    library.MARRIAGE_RITE_ID: "marriage",
}

EXPECTED_SECTION_KEYS = {
    library.FUNERAL_RITE_ID: {
        "funeral_greeting",
        "funeral_thanksgiving_for_baptism",
        "funeral_prayer_of_the_day",
        "funeral_apostles_creed",
        "funeral_commendation",
    },
    library.MARRIAGE_RITE_ID: {
        "marriage_greeting",
        "marriage_introduction",
        "marriage_declaration_of_intention",
        "marriage_prayer",
        "marriage_vows",
        "marriage_giving_of_rings",
        "marriage_acclamation",
        "marriage_blessing_of_couple",
    },
}

EXPECTED_VARIABLES = {
    library.FUNERAL_RITE_ID: {"deceased_name": ("text", True)},
    library.MARRIAGE_RITE_ID: {
        "partner_one": ("text", True),
        "partner_two": ("text", True),
        "wedding_date": ("date", False),
    },
}


def _section_keys(rite):
    return {
        block.data["section_key"]
        for block in rite.blocks
        if block.type == "canonical_slot"
    }


@pytest.mark.parametrize("rite_id", RITE_IDS)
def test_rite_loads(rite_id):
    rite = library.load_rite(rite_id)
    assert rite.id == rite_id
    assert rite.tradition == "elca"
    assert rite.occasion == EXPECTED_OCCASION[rite_id]


@pytest.mark.parametrize("rite_id", RITE_IDS)
def test_rite_validates(rite_id):
    rite = library.load_rite(rite_id)
    modules = library.load_modules()
    validate_rite(rite, modules=modules)


def test_rites_validated_at_library_import():
    library.validate_library()


@pytest.mark.parametrize("rite_id", RITE_IDS)
def test_rite_round_trips_against_its_json(rite_id):
    raw = json.loads((library.LIBRARY_DIR / (rite_id + ".json")).read_text())
    rite = library.load_rite(rite_id)
    assert rite.to_dict() == raw


@pytest.mark.parametrize("rite_id", RITE_IDS)
def test_text_and_module_refs_resolve(rite_id):
    rite = library.load_rite(rite_id)
    modules = library.load_modules()
    for block in rite.blocks:
        for ref in _text_refs_in_block(block):
            assert has_text(ref), "unresolved text key %r" % ref
            get_text(ref)
        if block.type == "module_ref":
            assert block.data.get("module_id") in modules


@pytest.mark.parametrize("rite_id", RITE_IDS)
def test_declared_variables_match_expected(rite_id):
    rite = library.load_rite(rite_id)
    declared = {v.key: (v.type, v.required) for v in rite.variables}
    assert declared == EXPECTED_VARIABLES[rite_id]


@pytest.mark.parametrize("rite_id", RITE_IDS)
def test_section_keys_match_expected(rite_id):
    rite = library.load_rite(rite_id)
    assert _section_keys(rite) == EXPECTED_SECTION_KEYS[rite_id]


@pytest.mark.parametrize("rite_id", RITE_IDS)
def test_canonical_slots_resolve_to_placeholder_without_church_text(rite_id):
    rite = library.load_rite(rite_id)
    context = ContentContext()
    for block in rite.blocks:
        if block.type != "canonical_slot":
            continue
        assert resolve_canonical_slot(block, context) == ENTITLEMENT_PLACEHOLDER


@pytest.mark.parametrize("rite_id", RITE_IDS)
def test_canonical_slots_resolve_to_saved_church_text(rite_id):
    rite = library.load_rite(rite_id)
    for block in rite.blocks:
        if block.type != "canonical_slot":
            continue
        section_key = block.data["section_key"]
        saved = "custom text for %s" % section_key
        context = ContentContext(church_texts={section_key: saved})
        assert resolve_canonical_slot(block, context) == saved


@pytest.mark.parametrize("rite_id", RITE_IDS)
def test_uses_declared_variable_in_a_heading(rite_id):
    rite = library.load_rite(rite_id)
    headings = " ".join(
        block.data.get("text", "")
        for block in rite.blocks
        if block.type == "heading"
    )
    for key in EXPECTED_VARIABLES[rite_id]:
        if EXPECTED_VARIABLES[rite_id][key][1]:
            assert ("{{%s}}" % key) in headings, (
                "required variable %r unused in any heading" % key
            )
