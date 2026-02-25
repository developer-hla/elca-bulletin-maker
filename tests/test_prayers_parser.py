"""Tests for the prayers HTML parser."""

from __future__ import annotations

from bulletin_maker.renderer.prayers_parser import (
    parse_prayers_html,
    parse_prayers_response,
)


# ── Sample HTML fragments matching S&S format ────────────────────────

SIMPLE_PRAYERS_HTML = (
    '<div>'
    '<div class="body">'
    '<div>Faithful God, we come before you in prayer.</div>'
    '<div><strong>Your mercy is great.</strong></div>'
    '<div>We pray for the church and its mission.</div>'
    '<div><strong>Your mercy is great.</strong></div>'
    '<div>We give you thanks for all your gifts.</div>'
    '<div><strong>Amen.</strong></div>'
    '</div>'
    '</div>'
)

PRAYERS_WITH_RUBRIC = (
    '<div>'
    '<div class="rubric">A brief silence.</div>'
    '<div class="body">'
    '<div>God of mercy, hear our prayer.</div>'
    '<div><strong>Hear our prayer.</strong></div>'
    '</div>'
    '</div>'
)

PRAYERS_WITH_INTRO = (
    '<div>'
    '<div class="body">Let us pray for the whole people of God.</div>'
    '<div class="body">'
    '<div>We pray for healing.</div>'
    '<div><strong>Lord, hear our prayer.</strong></div>'
    '</div>'
    '</div>'
)


class TestParsePrayersHtml:
    def test_extracts_petitions(self):
        result = parse_prayers_html(SIMPLE_PRAYERS_HTML)
        assert len(result["petitions"]) == 2

    def test_petition_text(self):
        result = parse_prayers_html(SIMPLE_PRAYERS_HTML)
        assert "we come before you" in result["petitions"][0]["text"].lower()

    def test_petition_response(self):
        result = parse_prayers_html(SIMPLE_PRAYERS_HTML)
        assert "mercy is great" in result["petitions"][0]["response"]

    def test_closing_detected(self):
        result = parse_prayers_html(SIMPLE_PRAYERS_HTML)
        assert result["closing_text"]
        assert "amen" in result["closing_response"].lower()

    def test_brief_silence_detected(self):
        result = parse_prayers_html(PRAYERS_WITH_RUBRIC)
        assert result["brief_silence"] is True

    def test_intro_extracted(self):
        result = parse_prayers_html(PRAYERS_WITH_INTRO)
        assert "whole people" in result["intro"].lower()

    def test_empty_html(self):
        result = parse_prayers_html("")
        assert result["petitions"] == []
        assert result["intro"] == ""

    def test_returns_dict_keys(self):
        result = parse_prayers_html(SIMPLE_PRAYERS_HTML)
        expected_keys = {"intro", "brief_silence", "petitions",
                         "closing_text", "closing_response"}
        assert set(result.keys()) == expected_keys


class TestParsePrayersResponse:
    def test_extracts_response(self):
        html = '<p>text <strong>Your mercy is great.</strong> more</p>'
        assert parse_prayers_response(html) == "Your mercy is great."

    def test_skips_amen(self):
        html = '<p><strong>Amen.</strong> <strong>Hear our prayer.</strong></p>'
        assert parse_prayers_response(html) == "Hear our prayer."

    def test_default_when_no_strong(self):
        assert parse_prayers_response("<p>plain text</p>") == "Your mercy is great."

    def test_default_when_only_amen(self):
        html = '<p><strong>Amen.</strong></p>'
        assert parse_prayers_response(html) == "Your mercy is great."
