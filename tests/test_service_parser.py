"""Tests for the Sundays & Seasons whole-service parser (layer 2).

Structural only, against a SYNTHETIC S&S-shaped fixture — no copyrighted
liturgical prose is used or asserted.  The fixture mimics the real markup:
options are ``<strong>OPTION x:</strong>`` inside ``<div class="rubric">``,
each option's body follows in a ``<div class="hymnal">``, and plain rubrics /
bodies / nested emphasis appear between choices.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bulletin_maker.sns.service_parser import (
    SEGMENT_OPTIONS,
    SEGMENT_RUBRIC,
    SEGMENT_TEXT,
    parse_service,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sns_service_sample.html"


@pytest.fixture(scope="module")
def segments():
    return parse_service(FIXTURE.read_text())


def _groups(segments):
    return [s for s in segments if s.kind == SEGMENT_OPTIONS]


def test_option_groups_recovered(segments):
    groups = _groups(segments)
    labels = [[o.label for o in g.options] for g in groups]
    assert labels == [["A", "B"], ["A", "B", "C"], ["A", "B"]]


def test_label_reset_splits_adjacent_groups(segments):
    # A new "A" after a "C" must start a distinct group, not extend the prior one.
    groups = _groups(segments)
    assert len(groups) == 3
    assert [o.label for o in groups[1].options] == ["A", "B", "C"]
    assert [o.label for o in groups[2].options] == ["A", "B"]


def test_option_bodies_captured(segments):
    groups = _groups(segments)
    assert groups[0].options[0].body == "Body alpha line."
    assert groups[0].options[1].body == "Body bravo line."
    # A genuine no-content option (like "No introduction") has an empty body.
    assert groups[1].options[2].body == ""


def test_option_heading_incipit_captured(segments):
    assert _groups(segments)[0].options[0].heading == "Alpha incipit"


def test_nested_emphasis_does_not_split_body(segments):
    bodies = [s.text for s in segments if s.kind == SEGMENT_TEXT]
    assert any("emphasis" in b and b.startswith("Standalone body") for b in bodies)


def test_toplevel_emphasis_becomes_text_segment(segments):
    assert any(s.kind == SEGMENT_TEXT and s.text == "Amen." for s in segments)


def test_plain_rubrics_preserved(segments):
    rubrics = [s.text for s in segments if s.kind == SEGMENT_RUBRIC]
    assert "Intro rubric one." in rubrics
    assert "Middle rubric two." in rubrics


def test_no_option_marker_leaks_into_a_rubric(segments):
    # Every "OPTION x:" line must be parsed as an option, never a rubric.
    rubrics = [s.text for s in segments if s.kind == SEGMENT_RUBRIC]
    assert not any(r.upper().startswith("OPTION ") for r in rubrics)
