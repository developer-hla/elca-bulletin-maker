"""Tests for html_renderer helper functions."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bulletin_maker.sns.models import (
    SLOT_FIRST,
    SLOT_GOSPEL,
    SLOT_SECOND,
    DayContent,
    Reading,
    ServiceConfig,
)
from bulletin_maker.renderer.html_renderer import (
    _build_baptism_context,
    _build_common_context,
    _get_reading,
    _get_reading_with_override,
)
from bulletin_maker.renderer.season import LiturgicalSeason


def _make_day() -> DayContent:
    return DayContent(
        date="2026-2-22",
        title="First Sunday in Lent, Year A",
        introduction="",
        confession_html="",
        prayer_of_the_day_html="",
        gospel_acclamation="",
        readings=[
            Reading(label="First Reading", citation="Genesis 2:15-17", intro="", text_html="<p>First</p>"),
            Reading(label="Psalm", citation="Psalm 32", intro="", text_html="<p>Psalm</p>"),
            Reading(label="Second Reading", citation="Romans 5:12-19", intro="", text_html="<p>Second</p>"),
            Reading(label="Gospel", citation="Matthew 4:1-11", intro="", text_html="<p>Gospel</p>"),
        ],
    )


class TestGetReadingWithOverride:
    def test_no_override_returns_default(self):
        day = _make_day()
        config = ServiceConfig(date="2026-2-22", date_display="February 22, 2026")
        result = _get_reading_with_override(day, config, SLOT_FIRST)
        assert result is not None
        assert result.citation == "Genesis 2:15-17"

    def test_override_with_reading_object(self):
        day = _make_day()
        override = Reading(
            label="First Reading", citation="Genesis 2:15-25",
            intro="Expanded", text_html="<p>Custom</p>",
        )
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            reading_overrides={SLOT_FIRST: override},
        )
        result = _get_reading_with_override(day, config, SLOT_FIRST)
        assert result.citation == "Genesis 2:15-25"
        assert result.text_html == "<p>Custom</p>"

    def test_override_with_dict(self):
        day = _make_day()
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            reading_overrides={SLOT_GOSPEL: {
                "label": "Gospel",
                "citation": "John 3:16-21",
                "intro": "Custom intro",
                "text_html": "<p>Custom gospel</p>",
            }},
        )
        result = _get_reading_with_override(day, config, SLOT_GOSPEL)
        assert result.citation == "John 3:16-21"

    def test_override_only_affects_specified_slot(self):
        day = _make_day()
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            reading_overrides={SLOT_FIRST: {
                "label": "First Reading",
                "citation": "Custom",
                "intro": "",
                "text_html": "<p>Custom</p>",
            }},
        )
        # SLOT_SECOND should still return the default
        result = _get_reading_with_override(day, config, SLOT_SECOND)
        assert result.citation == "Romans 5:12-19"

    def test_none_overrides_treated_as_no_override(self):
        day = _make_day()
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            reading_overrides=None,
        )
        result = _get_reading_with_override(day, config, SLOT_FIRST)
        assert result.citation == "Genesis 2:15-17"


class TestBuildBaptismContext:
    def test_single_name(self):
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            include_baptism=True,
            baptism_candidate_names="John Smith",
        )
        ctx = _build_baptism_context(config)
        assert ctx["include_baptism"] is True
        assert len(ctx["baptism_formulas"]) == 1
        assert "John Smith" in ctx["baptism_formulas"][0]

    def test_multiple_names(self):
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            include_baptism=True,
            baptism_candidate_names="John Smith, Jane Doe",
        )
        ctx = _build_baptism_context(config)
        assert len(ctx["baptism_formulas"]) == 2
        assert "John Smith" in ctx["baptism_formulas"][0]
        assert "Jane Doe" in ctx["baptism_formulas"][1]

    def test_empty_names_uses_placeholder(self):
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            include_baptism=True,
            baptism_candidate_names="",
        )
        ctx = _build_baptism_context(config)
        assert len(ctx["baptism_formulas"]) == 1
        assert "___" in ctx["baptism_formulas"][0]

    def test_context_has_all_required_keys(self):
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            include_baptism=True,
            baptism_candidate_names="Test",
        )
        ctx = _build_baptism_context(config)
        expected_keys = {
            "include_baptism", "baptism_presentation",
            "baptism_renunciation", "baptism_profession",
            "baptism_flood_prayer", "baptism_formulas",
            "baptism_welcome", "baptism_welcome_response",
        }
        assert expected_keys.issubset(ctx.keys())


class TestBuildCommonContext:
    """_build_common_context() produces keys shared by all document types."""

    @patch("bulletin_maker.renderer.html_renderer.get_gospel_acclamation_image",
           side_effect=FileNotFoundError)
    def test_returns_expected_shared_keys(self, _mock_ga):
        day = _make_day()
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            creed_type="nicene", include_kyrie=True, canticle="glory_to_god",
            eucharistic_form="extended", include_memorial_acclamation=True,
            show_confession=True, show_nunc_dimittis=True,
        )
        ctx = _build_common_context(day, config, LiturgicalSeason.LENT)
        expected_keys = {
            "church_name", "church_address", "cover_image_uri",
            "date_display", "day_name",
            "welcome_message", "standing_instructions",
            "show_confession", "confession_entries",
            "is_lent", "invitation_to_lent_paragraphs",
            "prayer_of_day_html",
            "first_reading", "psalm_data", "second_reading",
            "ga_image_uri", "gospel",
            "include_baptism", "creed_name", "creed_stanzas",
            "prayers_response",
            "offertory_hymn_verses",
            "great_thanksgiving_preface",
            "eucharistic_form", "eucharistic_prayer_first_line",
            "eucharistic_prayer_lines", "words_of_institution_paragraphs",
            "has_memorial_acclamation", "memorial_acclamation",
            "eucharistic_prayer_closing_stanzas", "come_holy_spirit",
            "lords_prayer_stanzas",
            "invitation_to_communion_text",
            "show_nunc_dimittis",
            "offering_prayer_text", "prayer_after_communion_text",
            "blessing_lines", "dismissal_entries",
        }
        assert expected_keys.issubset(ctx.keys())

    @patch("bulletin_maker.renderer.html_renderer.get_gospel_acclamation_image",
           side_effect=FileNotFoundError)
    def test_nicene_creed_selected(self, _mock_ga):
        day = _make_day()
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            creed_type="nicene",
        )
        ctx = _build_common_context(day, config, LiturgicalSeason.LENT)
        assert ctx["creed_name"] == "NICENE CREED"
        assert ctx["is_lent"] is True

    @patch("bulletin_maker.renderer.html_renderer.get_gospel_acclamation_image",
           side_effect=FileNotFoundError)
    def test_apostles_creed_selected(self, _mock_ga):
        day = _make_day()
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            creed_type="apostles",
        )
        ctx = _build_common_context(day, config, LiturgicalSeason.PENTECOST)
        assert ctx["creed_name"] == "APOSTLES CREED"
        assert ctx["is_lent"] is False

    @patch("bulletin_maker.renderer.html_renderer.get_gospel_acclamation_image",
           side_effect=FileNotFoundError)
    def test_readings_resolved(self, _mock_ga):
        day = _make_day()
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
        )
        ctx = _build_common_context(day, config, LiturgicalSeason.LENT)
        assert ctx["first_reading"] is not None
        assert ctx["first_reading"]["citation"] == "Genesis 2:15-17"
        assert ctx["gospel"] is not None
        assert ctx["gospel"]["citation"] == "Matthew 4:1-11"
