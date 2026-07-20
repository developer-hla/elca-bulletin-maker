"""Tests for the ELW Service of the Word library rite (LWS occasion services).

Fast, DB-free: Service of the Word is authored purely by re-selecting and
reordering blocks that already exist in ``elw_sunday_communion.json`` (no new
liturgical text), so these tests focus on structural facts: it loads, it
validates referentially, and it differs from Holy Communion only by omitting
every Meal block while keeping ``offering`` and moving ``lords_prayer`` to
follow it.
"""

from __future__ import annotations

import json

from bulletin_maker.core import library
from bulletin_maker.core.rite import _text_refs_in_block, validate_rite
from bulletin_maker.core.text_catalog import get_text, has_text

# Meal-only block ids present in elw_sunday_communion.json that a Service of
# the Word must NOT contain (the Meal is the one structural thing omitted).
MEAL_ONLY_BLOCK_IDS = frozenset(
    {
        "offertory",
        "offertory_hymn",
        "offering_prayer",
        "great_thanksgiving",
        "preface",
        "congregation_sings_sanctus",
        "sanctus",
        "eucharistic_prayer_heading",
        "eucharistic_prayer_extended_praise",
        "words_of_institution",
        "memorial_acclamation_intro",
        "memorial_acclamation",
        "eucharistic_prayer_closing",
        "eucharistic_prayer_amen",
        "invitation_to_communion",
        "invitation_seated_rubric",
        "agnus_dei",
        "communion_hymn",
        "post_communion_stand_rubric",
        "post_communion_blessing",
        "nunc_dimittis",
        "prayer_after_communion",
    }
)


def _load_sotw():
    return library.load_rite(library.SERVICE_OF_THE_WORD_RITE_ID)


def test_service_of_the_word_loads():
    rite = _load_sotw()
    assert rite.id == library.SERVICE_OF_THE_WORD_RITE_ID
    assert rite.tradition == "elca"
    assert rite.occasion == "sunday"
    assert "DRAFT" in rite.name


def test_service_of_the_word_round_trips_against_its_json():
    raw = json.loads(
        (library.LIBRARY_DIR / "elw_service_of_the_word.json").read_text()
    )
    rite = _load_sotw()
    assert rite.to_dict() == raw


def test_service_of_the_word_validates():
    rite = _load_sotw()
    modules = library.load_modules()
    validate_rite(rite, modules=modules)


def test_service_of_the_word_validated_at_library_import():
    # validate_library() runs every library rite (including this one).
    library.validate_library()


def test_service_of_the_word_text_and_module_refs_resolve():
    rite = _load_sotw()
    modules = library.load_modules()
    for block in rite.blocks:
        for ref in _text_refs_in_block(block):
            assert has_text(ref), "unresolved text key %r" % ref
            get_text(ref)
        if block.type == "module_ref":
            assert block.data.get("module_id") in modules


def test_service_of_the_word_contains_no_meal_blocks():
    rite = _load_sotw()
    ids = {b.id for b in rite.blocks}
    overlap = ids & MEAL_ONLY_BLOCK_IDS
    assert not overlap, "Meal-only block(s) leaked into Service of the Word: %s" % sorted(
        overlap
    )


def test_service_of_the_word_retains_offering():
    rite = _load_sotw()
    ids = [b.id for b in rite.blocks]
    assert "offering" in ids


def test_service_of_the_word_lords_prayer_follows_offering():
    rite = _load_sotw()
    ids = [b.id for b in rite.blocks]
    assert "lords_prayer" in ids
    assert ids.index("lords_prayer") == ids.index("offering") + 1


def test_service_of_the_word_blocks_are_a_subset_reused_from_communion():
    """Every block id/type in the SotW rite already exists, unchanged, in the
    Holy Communion rite (only structure - selection/order - was authored)."""
    sotw = _load_sotw()
    communion = library.load_rite(library.SUNDAY_COMMUNION_RITE_ID)
    communion_by_id = {b.id: b for b in communion.blocks}

    for block in sotw.blocks:
        assert block.id in communion_by_id, (
            "SotW block %r has no counterpart in elw_sunday_communion.json"
            % block.id
        )
        source = communion_by_id[block.id]
        assert block.to_dict() == source.to_dict(), (
            "SotW block %r diverges from its Holy Communion source" % block.id
        )


def test_service_of_the_word_has_expected_block_count():
    # 36 reused blocks: full Communion ordo minus the 22 Meal-only blocks
    # (58 total blocks in elw_sunday_communion.json - 22 = 36).
    rite = _load_sotw()
    assert len(rite.blocks) == 36
