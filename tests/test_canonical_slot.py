"""Tests for the ``canonical_slot`` block type (skeleton layer).

Fast, DB-free.  A ``canonical_slot`` stores no copyrighted wording: it names a
stable ``section_key`` whose text is resolved at render time through
``content_source.resolve_text``.  With no church override and no live pull wired
(this layer), resolution returns the entitlement placeholder; a church-saved
custom text wins when present.  These tests assert the schema contract
(``section_key`` format, required field, referential validity) and the
resolution behaviour — never any liturgical prose.
"""

from __future__ import annotations

import pytest

import bulletin_maker.renderer  # noqa: F401  (warm the cold-import cycle)
from bulletin_maker.core.content_source import (
    ENTITLEMENT_PLACEHOLDER,
    ContentContext,
)
from bulletin_maker.core.rite import (
    Block,
    Rite,
    RiteSchemaError,
    validate_rite,
)
from bulletin_maker.renderer.rite_resolver import resolve_canonical_slot

SECTION_KEY = "funeral_greeting"


def _canonical_block(section_key: str = SECTION_KEY) -> Block:
    return Block.from_dict(
        {"id": "b1", "type": "canonical_slot", "section_key": section_key}
    )


def test_canonical_slot_without_church_text_resolves_to_placeholder():
    block = _canonical_block()
    resolved = resolve_canonical_slot(block, ContentContext())
    assert resolved == ENTITLEMENT_PLACEHOLDER


def test_canonical_slot_with_church_text_resolves_to_that_text():
    saved = "A church-saved custom text for this section."
    context = ContentContext(church_texts={SECTION_KEY: saved})
    block = _canonical_block()
    assert resolve_canonical_slot(block, context) == saved


def test_canonical_slot_unentitled_still_yields_placeholder():
    block = _canonical_block()
    resolved = resolve_canonical_slot(block, ContentContext(entitled=False))
    assert resolved == ENTITLEMENT_PLACEHOLDER


@pytest.mark.parametrize(
    "section_key", ["funeral_greeting", "_private", "marriage_vows", "a1"]
)
def test_valid_section_keys_accepted(section_key):
    block = _canonical_block(section_key)
    assert block.data["section_key"] == section_key


@pytest.mark.parametrize(
    "section_key", ["1leading_digit", "has-dash", "has space", "has.dot", ""]
)
def test_malformed_section_key_rejected(section_key):
    with pytest.raises(RiteSchemaError):
        _canonical_block(section_key)


def test_canonical_slot_requires_section_key():
    with pytest.raises(RiteSchemaError):
        Block.from_dict({"id": "b1", "type": "canonical_slot"})


def test_validate_rite_accepts_wellformed_canonical_slot():
    rite = Rite(id="r1", name="R1", blocks=[_canonical_block()])
    validate_rite(rite, catalog=frozenset(), modules={})


def test_canonical_slot_roundtrips():
    block = _canonical_block()
    assert Block.from_dict(block.to_dict()).to_dict() == block.to_dict()
