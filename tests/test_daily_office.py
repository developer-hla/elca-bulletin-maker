"""Tests for the three ELW Daily Office library rites (LWS occasion services).

Fast, DB-free.  The Daily Office rites (Morning Prayer / Evening Prayer /
Night Prayer) are authored as DRAFT ordos that bundle genuinely public-domain
text (KJV canticles, 1662 BCP versicles/Gloria Patri/General Confession,
Bridges' 1899 Phos Hilaron, traditional Compline material) via new ``pd.*``
catalog keys, while leaving ELW's copyrighted contemporary wording as
[VAR]/[LIC] slots.  These tests assert structural facts: each office loads,
validates referentially, round-trips against its JSON, every text/module ref
resolves, the gospel canticles are present via ``pd.*`` keys, and no bundled
``pd.*`` constant is empty.
"""

from __future__ import annotations

import json

import pytest

from bulletin_maker.core import library
from bulletin_maker.core.rite import _text_refs_in_block, validate_rite
from bulletin_maker.core.text_catalog import get_text, has_text, text_keys

OFFICE_RITE_IDS = (
    library.MORNING_PRAYER_RITE_ID,
    library.EVENING_PRAYER_RITE_ID,
    library.NIGHT_PRAYER_RITE_ID,
)

# The gospel canticle each office must carry, keyed by rite id.
OFFICE_CANTICLE_KEY = {
    library.MORNING_PRAYER_RITE_ID: "pd.benedictus_kjv",
    library.EVENING_PRAYER_RITE_ID: "pd.magnificat_kjv",
    library.NIGHT_PRAYER_RITE_ID: "pd.nunc_dimittis_kjv",
}

PD_CANTICLE_KEYS = (
    "pd.benedictus_kjv",
    "pd.magnificat_kjv",
    "pd.nunc_dimittis_kjv",
    "pd.te_deum_bcp1662",
)


def _text_refs(rite):
    return [ref for block in rite.blocks for ref in _text_refs_in_block(block)]


@pytest.mark.parametrize("rite_id", OFFICE_RITE_IDS)
def test_office_loads(rite_id):
    rite = library.load_rite(rite_id)
    assert rite.id == rite_id
    assert rite.tradition == "elca"
    assert rite.occasion == "daily_office"
    assert "DRAFT" in rite.name


@pytest.mark.parametrize("rite_id", OFFICE_RITE_IDS)
def test_office_validates(rite_id):
    rite = library.load_rite(rite_id)
    modules = library.load_modules()
    validate_rite(rite, modules=modules)


@pytest.mark.parametrize("rite_id", OFFICE_RITE_IDS)
def test_office_round_trips_against_its_json(rite_id):
    raw = json.loads((library.LIBRARY_DIR / (rite_id + ".json")).read_text())
    rite = library.load_rite(rite_id)
    assert rite.to_dict() == raw


def test_offices_validated_at_library_import():
    # validate_library() runs every library rite, including the three offices.
    library.validate_library()


@pytest.mark.parametrize("rite_id", OFFICE_RITE_IDS)
def test_office_text_and_module_refs_resolve(rite_id):
    rite = library.load_rite(rite_id)
    modules = library.load_modules()
    for block in rite.blocks:
        for ref in _text_refs_in_block(block):
            assert has_text(ref), "unresolved text key %r" % ref
            get_text(ref)
        if block.type == "module_ref":
            assert block.data.get("module_id") in modules


@pytest.mark.parametrize("rite_id", OFFICE_RITE_IDS)
def test_office_carries_its_gospel_canticle_via_pd_key(rite_id):
    rite = library.load_rite(rite_id)
    expected = OFFICE_CANTICLE_KEY[rite_id]
    assert expected in _text_refs(rite), (
        "%s must reference its gospel canticle via %r" % (rite_id, expected)
    )


def test_offices_only_reference_pd_or_reusable_keys():
    """Bundled office text must be PD (pd.*) or the traditional-wording Lord's
    Prayer (elw.lords_prayer, itself the public-domain 'Our Father' constant).
    No other elw.* copyrighted wording is bundled into the offices."""
    allowed = {"elw.lords_prayer"}
    for rite_id in OFFICE_RITE_IDS:
        rite = library.load_rite(rite_id)
        for ref in _text_refs(rite):
            assert ref.startswith("pd.") or ref in allowed, (
                "%s bundles non-PD text key %r" % (rite_id, ref)
            )


def test_pd_catalog_keys_are_present():
    keys = text_keys()
    for key in PD_CANTICLE_KEYS:
        assert key in keys
    for key in (
        "pd.phos_hilaron_bridges",
        "pd.versicle_open_lips",
        "pd.versicle_make_speed",
        "pd.gloria_patri",
        "pd.general_confession_bcp",
        "pd.compline_open",
        "pd.into_thy_hands",
    ):
        assert key in keys


def test_no_pd_constant_is_empty():
    for key in text_keys():
        if not key.startswith("pd."):
            continue
        value = get_text(key)
        assert value, "pd.* constant %r is empty" % key
        if isinstance(value, str):
            assert value.strip(), "pd.* string %r is blank" % key
        else:
            for role, text in value:
                assert text.strip(), "pd.* dialog %r has a blank line" % key
