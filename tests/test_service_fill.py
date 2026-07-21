"""Tests for the layer-2 runtime service-fill pipeline.

Structural only.  Fills are proven against the SYNTHETIC S&S-shaped fixture
(``tests/fixtures/sns_service_sample.html``) and against tiny synthetic
placeholder documents built inline; NO copyrighted liturgical prose is used or
asserted.  ``sns_fetch_raw`` is monkeypatched to return that synthetic markup, and
the section-index/kind map is overridden with synthetic entries (or exploits a
known fixture-index alignment) so the fill / confidence / interpolation paths
are exercised without touching any real S&S document.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import bulletin_maker.renderer  # noqa: F401  (warm the cold-import cycle)
from bulletin_maker.core.content_source import (
    ENTITLEMENT_PLACEHOLDER,
    ContentContext,
)
from bulletin_maker.core.rite import Block
from bulletin_maker.renderer.rite_resolver import resolve_canonical_slot
from bulletin_maker.sns import service_fill
from bulletin_maker.sns.service_fill import fill_section
from bulletin_maker.sns.service_parser import SEGMENT_OPTIONS, SEGMENT_TEXT

FIXTURE = Path(__file__).parent / "fixtures" / "sns_service_sample.html"
FIXTURE_HTML = FIXTURE.read_text()

# Known parse layout of the fixture (see test_service_parser):
#   1 -> options (default body "Body alpha line.")
#   2 -> rubric
#   3 -> text ("Standalone body with emphasis inside it.")
FIXTURE_OPTION_BODY = "Body alpha line."
FIXTURE_TEXT_INDEX_3 = "Standalone body with emphasis inside it."

SYN_ATOM = "syn_atom"
SYN_MAP = {
    "syn_options": (SYN_ATOM, 1, SEGMENT_OPTIONS),
    "syn_text": (SYN_ATOM, 3, SEGMENT_TEXT),
    "syn_wrong_kind": (SYN_ATOM, 2, SEGMENT_TEXT),
    "syn_out_of_range": (SYN_ATOM, 99, SEGMENT_TEXT),
}


@pytest.fixture(autouse=True)
def _clear_parse_cache():
    service_fill._parse_cached.cache_clear()
    yield
    service_fill._parse_cached.cache_clear()


@pytest.fixture
def syn_map(monkeypatch):
    monkeypatch.setattr(service_fill, "SECTION_MAP", SYN_MAP)
    return SYN_MAP


def _ctx(html, *, entitled=True, variables=None):
    return ContentContext(
        entitled=entitled,
        sns_fetch_raw=lambda atom_code: html,
        variables=variables or {},
    )


def test_options_section_fills_from_default_option(syn_map):
    assert fill_section("syn_options", _ctx(FIXTURE_HTML)) == FIXTURE_OPTION_BODY


def test_text_section_fills_from_segment_text(syn_map):
    assert fill_section("syn_text", _ctx(FIXTURE_HTML)) == FIXTURE_TEXT_INDEX_3


def test_wrong_kind_at_index_returns_none_and_warns(syn_map, caplog):
    with caplog.at_level("WARNING"):
        result = fill_section("syn_wrong_kind", _ctx(FIXTURE_HTML))
    assert result is None
    assert SYN_ATOM in caplog.text and "syn_wrong_kind" in caplog.text


def test_out_of_range_index_returns_none_and_warns(syn_map, caplog):
    with caplog.at_level("WARNING"):
        result = fill_section("syn_out_of_range", _ctx(FIXTURE_HTML))
    assert result is None
    assert "syn_out_of_range" in caplog.text


def test_unmapped_key_returns_none(syn_map):
    assert fill_section("not_a_mapped_section", _ctx(FIXTURE_HTML)) is None


def test_unentitled_returns_none_and_never_pulls(syn_map):
    fetch = MagicMock(return_value=FIXTURE_HTML)
    context = ContentContext(entitled=False, sns_fetch_raw=fetch)
    assert fill_section("syn_options", context) is None
    fetch.assert_not_called()


def test_no_fetch_hook_returns_none(syn_map):
    assert fill_section("syn_options", ContentContext(sns_fetch_raw=None)) is None


def test_empty_pull_returns_none_and_warns(syn_map, caplog):
    with caplog.at_level("WARNING"):
        result = fill_section("syn_options", _ctx(""))
    assert result is None


def test_couple_placeholder_interpolated(monkeypatch):
    marriage_map = {"marriage_syn": (SYN_ATOM, 0, SEGMENT_TEXT)}
    monkeypatch.setattr(service_fill, "SECTION_MAP", marriage_map)
    html = '<div class="body">Bless name and name today.</div>'
    context = _ctx(html, variables={"partner_one": "Alex", "partner_two": "Sam"})
    assert fill_section("marriage_syn", context) == "Bless Alex and Sam today."


def test_couple_placeholder_left_verbatim_when_partner_missing(monkeypatch, caplog):
    marriage_map = {"marriage_syn": (SYN_ATOM, 0, SEGMENT_TEXT)}
    monkeypatch.setattr(service_fill, "SECTION_MAP", marriage_map)
    html = '<div class="body">Bless name and name today.</div>'
    context = _ctx(html, variables={"partner_one": "Alex"})
    with caplog.at_level("WARNING"):
        result = fill_section("marriage_syn", context)
    assert result == "Bless name and name today."
    assert "marriage_syn" in caplog.text


def test_funeral_name_token_interpolated_and_name_of_guarded(monkeypatch):
    funeral_map = {"funeral_syn": (SYN_ATOM, 0, SEGMENT_TEXT)}
    monkeypatch.setattr(service_fill, "SECTION_MAP", funeral_map)
    html = '<div class="body">We commend name in the name of God.</div>'
    context = _ctx(html, variables={"deceased_name": "Chris"})
    assert (
        fill_section("funeral_syn", context)
        == "We commend Chris in the name of God."
    )


def _canonical_block(section_key):
    return Block.from_dict(
        {"id": "b1", "type": "canonical_slot", "section_key": section_key}
    )


def test_resolve_canonical_slot_fills_from_service(monkeypatch):
    # marriage_greeting maps to a "text" segment at index 3, matching the
    # fixture's layout, so the real mapping fills from the pulled document.
    block = _canonical_block("marriage_greeting")
    context = _ctx(FIXTURE_HTML)
    assert resolve_canonical_slot(block, context) == FIXTURE_TEXT_INDEX_3


def test_resolve_canonical_slot_church_text_wins_without_pull():
    fetch = MagicMock(return_value=FIXTURE_HTML)
    saved = "A church-saved custom greeting."
    context = ContentContext(
        entitled=True, sns_fetch_raw=fetch,
        church_texts={"marriage_greeting": saved},
    )
    block = _canonical_block("marriage_greeting")
    assert resolve_canonical_slot(block, context) == saved
    fetch.assert_not_called()


def test_resolve_canonical_slot_unentitled_yields_placeholder():
    block = _canonical_block("marriage_greeting")
    context = ContentContext(entitled=False, sns_fetch_raw=lambda a: FIXTURE_HTML)
    assert resolve_canonical_slot(block, context) == ENTITLEMENT_PLACEHOLDER


def test_resolve_canonical_slot_fill_failure_yields_placeholder():
    # funeral_greeting expects "options" at index 2, but the fixture has a
    # rubric there -> confidence check fails -> placeholder.
    block = _canonical_block("funeral_greeting")
    context = _ctx(FIXTURE_HTML)
    assert resolve_canonical_slot(block, context) == ENTITLEMENT_PLACEHOLDER


def test_resolve_canonical_slot_unmapped_key_uses_resolve_text():
    # A non-SECTION_MAP canonical_slot key keeps its old resolve_text behaviour:
    # a church override still wins through resolve_text, untouched by the fill.
    saved = "Custom text for an unmapped section."
    context = ContentContext(church_texts={"some_unmapped_section": saved})
    block = _canonical_block("some_unmapped_section")
    assert resolve_canonical_slot(block, context) == saved
