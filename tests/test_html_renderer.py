"""Tests for html_renderer helper functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.exceptions import ContentNotFoundError, NetworkError
from bulletin_maker.sns.models import (
    SLOT_FIRST,
    SLOT_GOSPEL,
    SLOT_SECOND,
    DayContent,
    HymnLyrics,
    Reading,
)
from bulletin_maker.renderer.html_renderer import (
    AdjustProfile,
    BULLETIN_LOOSEN_PROFILES,
    BULLETIN_TIGHTEN_PROFILES,
    _best_direction,
    _booklet_blanks,
    _build_baptism_context,
    _build_bulletin_context,
    _build_common_context,
    _build_large_print_context,
    _canticle_image_uri_for_config,
    _canticle_text_for_config,
    _fetch_hymn_image_uri,
    _get_reading,
    _get_reading_with_override,
    _hymn_title_str,
    _inject_css,
    _load_offertory_image_uri,
)
from bulletin_maker.renderer.filters import setup_jinja_env
from bulletin_maker.core.static_text import (
    GLORY_TO_GOD_TEXT,
    INVITATION_TO_COMMUNION,
    MEMORIAL_ACCLAMATION,
    THIS_IS_THE_FEAST_TEXT,
)
from bulletin_maker.sns.models import (
    CANTICLE_GLORY_TO_GOD,
    CANTICLE_NONE,
    CANTICLE_THIS_IS_THE_FEAST,
)
from bulletin_maker.renderer.season import LiturgicalSeason
from bulletin_maker.core.text_utils import DialogRole


def _render_seq(*block_ids: str) -> list:
    """Minimal rite-driven render sequence for template tests.

    Both bulletin.html (`bulletin_sequence`) and large_print.html
    (`large_print_sequence`) iterate a resolved sequence; tests that render a
    template with a hand-built context supply just the block ids they check.
    A template ignores the other document's sequence key, so parametrized tests
    can pass both.
    """
    return [{"flow": False, "ids": list(block_ids)}]


def _canticle_config(canticle: str | None) -> ServiceConfig:
    """Minimal ServiceConfig for canticle helper tests."""
    return ServiceConfig(
        date="2026-01-01", date_display="January 1, 2026", canticle=canticle,
    )


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
            variables={"baptism_candidate_names": "John Smith"},
        )
        ctx = _build_baptism_context(config)
        assert ctx["include_baptism"] is True
        assert len(ctx["baptism_formulas"]) == 1
        assert "John Smith" in ctx["baptism_formulas"][0]

    def test_multiple_names(self):
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            include_baptism=True,
            variables={"baptism_candidate_names": "John Smith, Jane Doe"},
        )
        ctx = _build_baptism_context(config)
        assert len(ctx["baptism_formulas"]) == 2
        assert "John Smith" in ctx["baptism_formulas"][0]
        assert "Jane Doe" in ctx["baptism_formulas"][1]

    def test_empty_names_uses_placeholder(self):
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            include_baptism=True,
            variables={"baptism_candidate_names": ""},
        )
        ctx = _build_baptism_context(config)
        assert len(ctx["baptism_formulas"]) == 1
        assert "___" in ctx["baptism_formulas"][0]

    def test_context_has_all_required_keys(self):
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
            include_baptism=True,
            variables={"baptism_candidate_names": "Test"},
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
        ctx = _build_common_context(day, config, LiturgicalSeason.LENT.value)
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
            "has_memorial_acclamation", "memorial_acclamation_mode",
            "memorial_acclamation",
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
        ctx = _build_common_context(day, config, LiturgicalSeason.LENT.value)
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
        ctx = _build_common_context(day, config, LiturgicalSeason.PENTECOST.value)
        assert ctx["creed_name"] == "APOSTLES CREED"
        assert ctx["is_lent"] is False

    @patch("bulletin_maker.renderer.html_renderer.get_gospel_acclamation_image",
           side_effect=FileNotFoundError)
    def test_readings_resolved(self, _mock_ga):
        day = _make_day()
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
        )
        ctx = _build_common_context(day, config, LiturgicalSeason.LENT.value)
        assert ctx["first_reading"] is not None
        assert ctx["first_reading"]["citation"] == "Genesis 2:15-17"
        assert ctx["gospel"] is not None
        assert ctx["gospel"]["citation"] == "Matthew 4:1-11"

    @patch("bulletin_maker.renderer.html_renderer.get_gospel_acclamation_image",
           side_effect=FileNotFoundError)
    def test_invitation_to_communion_uses_ascension_text(self, _mock_ga):
        day = _make_day()
        day.invitation_to_communion = "<p>S&S invitation should not render.</p>"
        config = ServiceConfig(
            date="2026-2-22", date_display="February 22, 2026",
        )
        ctx = _build_common_context(day, config, LiturgicalSeason.LENT.value)

        assert ctx["invitation_to_communion_text"] == INVITATION_TO_COMMUNION


class TestBulletinTemplate:
    """Template behavior for congregation bulletin-specific rendering."""

    def _render_memorial_acclamation(self, image_uri: str, mode: str) -> str:
        env = setup_jinja_env()
        template = env.get_template("bulletin.html")
        return template.render(
            bulletin_sequence=_render_seq("memorial_acclamation"),
            css="",
            church_address="",
            eucharistic_form="extended",
            eucharistic_prayer_first_line="",
            eucharistic_prayer_lines=[],
            words_of_institution_paragraphs=[],
            has_memorial_acclamation=True,
            memorial_acclamation_mode=mode,
            memorial_acclamation=MEMORIAL_ACCLAMATION,
            memorial_acclamation_image_uri=image_uri,
            eucharistic_prayer_closing_stanzas=[],
            lords_prayer_stanzas=[],
            dismissal_entries=[],
        )

    def test_memorial_acclamation_uses_image_instead_of_text(self):
        html = self._render_memorial_acclamation(
            "data:image/jpeg;base64,test", "sung",
        )

        assert 'alt="Memorial Acclamation"' in html
        assert "Christ has died" not in html

    def test_spoken_memorial_acclamation_uses_text_instead_of_image(self):
        html = self._render_memorial_acclamation(
            "data:image/jpeg;base64,test", "spoken",
        )

        assert 'alt="Memorial Acclamation"' not in html
        assert "Christ has died" in html

    def test_memorial_acclamation_text_fallback_without_image(self):
        html = self._render_memorial_acclamation("", "sung")

        assert 'alt="Memorial Acclamation"' not in html
        assert "Christ has died" in html

    def test_bulletin_choral_call_includes_composer(self):
        env = setup_jinja_env()
        template = env.get_template("bulletin.html")
        html = template.render(
            bulletin_sequence=_render_seq("choral_call_to_worship"),
            css="",
            church_address="",
            choral_title="Create in Me a Clean Heart",
            choral_composer="Carl Mueller",
            eucharistic_form="short",
            lords_prayer_stanzas=[],
            dismissal_entries=[],
        )

        assert "Create in Me a Clean Heart" in html
        assert "Carl Mueller" in html

    def test_large_print_choral_call_includes_composer(self):
        env = setup_jinja_env()
        template = env.get_template("large_print.html")
        html = template.render(
            large_print_sequence=_render_seq("choral_call_to_worship"),
            css="",
            church_address="",
            choral_title="Create in Me a Clean Heart",
            choral_composer="Carl Mueller",
            eucharistic_form="short",
            lords_prayer_stanzas=[],
            dismissal_entries=[],
        )

        assert "Create in Me a Clean Heart" in html
        assert "Carl Mueller" in html

    @pytest.mark.parametrize("template_name", ["bulletin.html", "large_print.html"])
    def test_psalm_does_not_include_reading_response(self, template_name):
        env = setup_jinja_env()
        template = env.get_template(template_name)
        html = template.render(
            bulletin_sequence=_render_seq("psalm"),
            large_print_sequence=_render_seq("psalm"),
            css="",
            church_address="",
            psalm_data={
                "number": "32",
                "intro": "",
                "verses": [
                    {
                        "verse_num": "1",
                        "text": "Happy are they whose transgressions are forgiven.",
                        "bold": False,
                        "continuation": False,
                        "continuations": [],
                    },
                ],
            },
            eucharistic_form="short",
            lords_prayer_stanzas=[],
            dismissal_entries=[],
        )

        assert "Happy are they whose transgressions are forgiven." in html
        assert "The word of the Lord." not in html
        assert "Thanks be to God." not in html

    @pytest.mark.parametrize("template_name,prelude_markup,heading_markup", [
        ("bulletin.html", "<em>Prelude on AZMON</em>", "<span>WELCOME</span>"),
        ("large_print.html", ">Prelude on AZMON", "<span>WELCOME</span>"),
    ])
    def test_choral_call_follows_prelude(self, template_name, prelude_markup, heading_markup):
        env = setup_jinja_env()
        template = env.get_template(template_name)
        # `welcome_spoken` is a `heading`: universally type-dispatched, so it
        # arrives as an embedded unit (rendered via the render_block macro),
        # not a bare id.
        welcome_spoken = {
            "embedded": True, "type": "heading", "id": "welcome_spoken",
            "text": "WELCOME", "spacer": True,
        }
        html = template.render(
            bulletin_sequence=_render_seq(
                "prelude", "choral_call_to_worship", welcome_spoken,
            ),
            large_print_sequence=_render_seq(
                "prelude", "choral_call_to_worship", welcome_spoken,
            ),
            css="",
            church_address="",
            prelude_title="Prelude on AZMON",
            choral_title="Create in Me a Clean Heart",
            eucharistic_form="short",
            lords_prayer_stanzas=[],
            dismissal_entries=[],
        )

        prelude_index = html.index(prelude_markup)
        choral_index = html.index("CHORAL CALL TO WORSHIP")
        welcome_index = html.index(heading_markup, choral_index)
        assert prelude_index < choral_index < welcome_index

    @patch("bulletin_maker.renderer.html_renderer._safe_setting_image_uri", return_value="")
    @patch("bulletin_maker.renderer.html_renderer._load_offertory_image_uri", return_value="")
    @patch("bulletin_maker.renderer.html_renderer.get_gospel_acclamation_image",
           side_effect=FileNotFoundError)
    def test_bulletin_service_music_includes_composer(self, *_mocks):
        env = setup_jinja_env()
        template = env.get_template("bulletin.html")
        config = ServiceConfig(
            date="2026-05-10",
            date_display="May 10, 2026",
            prelude_title="Prelude on AZMON",
            prelude_composer="J.S. Bach",
            prelude_performer="Organist",
            postlude_title="Toccata",
            postlude_composer="Charles-Marie Widor",
            postlude_performer="Organist",
        )
        ctx = _build_bulletin_context(_make_day(), config, LiturgicalSeason.EASTER.value)
        html = template.render(**ctx)

        assert "<span>PRELUDE</span>" in html
        assert "<em>Prelude on AZMON</em> &mdash; J.S. Bach / Organist" in html
        assert "<span>*POSTLUDE</span>" in html
        assert "<em>Toccata</em> &mdash; Charles-Marie Widor / Organist" in html

    @patch("bulletin_maker.renderer.html_renderer._safe_setting_image_uri", return_value="")
    @patch("bulletin_maker.renderer.html_renderer._load_offertory_image_uri", return_value="")
    @patch("bulletin_maker.renderer.html_renderer.get_gospel_acclamation_image",
           side_effect=FileNotFoundError)
    def test_bulletin_offering_music_can_be_choral_anthem(self, *_mocks):
        env = setup_jinja_env()
        template = env.get_template("bulletin.html")
        config = ServiceConfig(
            date="2026-05-10",
            date_display="May 10, 2026",
            offertory_type="choral_anthem",
            offertory_title="God Is Still Speaking",
            offertory_composer="Marty Haugen",
            offertory_performer="Emery Lewis, soloist",
        )
        ctx = _build_bulletin_context(_make_day(), config, LiturgicalSeason.EASTER.value)
        html = template.render(**ctx)

        assert "<span>CHORAL ANTHEM</span>" in html
        assert "God Is Still Speaking" in html
        assert "Marty Haugen" in html
        assert "Emery Lewis, soloist" in html

    @patch("bulletin_maker.renderer.html_renderer._load_offertory_image_uri", return_value="")
    @patch("bulletin_maker.renderer.html_renderer.get_gospel_acclamation_image",
           side_effect=FileNotFoundError)
    def test_large_print_offering_music_can_be_choral_anthem(self, *_mocks):
        env = setup_jinja_env()
        template = env.get_template("large_print.html")
        config = ServiceConfig(
            date="2026-05-10",
            date_display="May 10, 2026",
            offertory_type="choral_anthem",
            offertory_title="God Is Still Speaking",
            offertory_composer="Marty Haugen",
            offertory_performer="Emery Lewis, soloist",
        )
        ctx = _build_large_print_context(_make_day(), config, LiturgicalSeason.EASTER.value)
        html = template.render(**ctx)

        assert "<span>CHORAL ANTHEM</span>" in html
        assert "God Is Still Speaking" in html
        assert "Marty Haugen" in html
        assert "Emery Lewis, soloist" in html

    def test_bulletin_confession_splits_terminal_amen(self):
        env = setup_jinja_env()
        template = env.get_template("bulletin.html")
        html = template.render(
            bulletin_sequence=_render_seq("confession"),
            css="",
            church_address="",
            show_confession=True,
            confession_entries=[
                (DialogRole.PASTOR, "In the name of the Holy Spirit. Amen."),
                (DialogRole.CONGREGATION, "to the glory of your holy name. Amen."),
            ],
            eucharistic_form="short",
            lords_prayer_stanzas=[],
            dismissal_entries=[],
        )

        assert "Holy Spirit.<br>\n<strong>Amen.</strong>" in html
        assert "holy name.<br>\nAmen." in html

    def test_blessing_splits_terminal_amen(self):
        env = setup_jinja_env()
        template = env.get_template("bulletin.html")
        html = template.render(
            bulletin_sequence=_render_seq("blessing"),
            css="",
            church_address="",
            show_confession=False,
            blessing_lines=["The Lord give you peace. Amen."],
            eucharistic_form="short",
            lords_prayer_stanzas=[],
            dismissal_entries=[],
        )

        assert "The Lord give you peace.<br>\n<strong>Amen.</strong>" in html

    def test_bulletin_prayers_bold_terminal_amen_without_bolding_pastor_lines(self):
        env = setup_jinja_env()
        template = env.get_template("bulletin.html")
        html = template.render(
            bulletin_sequence=_render_seq(
                "prayer_of_day", "peace", "offering_prayer", "lords_prayer",
                "invitation_to_communion", "prayer_after_communion",
            ),
            css="",
            church_address="",
            show_confession=False,
            prayer_of_day_html="<p>Through Christ our Lord. Amen.</p>",
            offering_prayer_text="Receive these gifts. Amen.",
            prayer_after_communion_text="Send us in peace.\nAmen.",
            invitation_to_communion_text="Come to the table.",
            eucharistic_form="short",
            words_of_institution_paragraphs=[],
            lords_prayer_stanzas=["forever and ever. Amen."],
            blessing_lines=[],
            dismissal_entries=[],
        )

        assert "Through Christ our Lord.<br>\n<strong>Amen.</strong></p>" in html
        assert "Receive these gifts.<br>\n<strong>Amen.</strong>" in html
        assert "Send us in peace.<br>\n<strong>Amen.</strong>" in html
        assert "forever and ever.<br>\n<strong>Amen.</strong>" in html
        assert (
            '<span class="role-label">P: </span><strong>The peace of Christ'
            not in html
        )
        assert '<span class="role-label">P: </span>The peace of Christ' in html
        assert (
            '<span class="role-label">P: </span><strong>Gathered into one'
            not in html
        )
        assert '<span class="role-label">P: </span>Gathered into one' in html
        assert (
            '<span class="role-label">P: </span><strong>Come to the table.'
            not in html
        )
        assert '<span class="role-label">P: </span>Come to the table.' in html

    def test_large_print_great_thanksgiving_bolds_only_congregation_response(self):
        env = setup_jinja_env()
        template = env.get_template("large_print.html")
        html = template.render(
            large_print_sequence=_render_seq(
                "prayer_of_day", "great_thanksgiving", "peace",
            ),
            css="",
            church_address="",
            show_confession=False,
            prayer_of_day_html="<p>Through Christ our Lord. Amen.</p>",
            invitation_to_communion_text="Come to the table.",
            great_thanksgiving_dialog=[
                (DialogRole.PASTOR, "The Lord be with you."),
                (DialogRole.CONGREGATION, "And also with you."),
            ],
            eucharistic_form="short",
            words_of_institution_paragraphs=[],
            lords_prayer_stanzas=[],
            sanctus_stanzas=[],
            agnus_dei_stanzas=[],
            blessing_lines=[],
            dismissal_entries=[],
        )

        assert "<strong>The Lord be with you.</strong>" not in html
        assert "<strong>And also with you.</strong>" in html
        assert "Through Christ our Lord.<br>\n<strong>Amen.</strong></p>" in html
        assert (
            '<span class="role-label">P: </span><strong>The peace of Christ'
            not in html
        )
        assert '<span class="role-label">P: </span>The peace of Christ' in html


class TestHymnTitleStr:
    """Congregation bulletin hymn heading formatting."""

    def test_none_returns_empty(self):
        assert _hymn_title_str(None) == ""

    def test_includes_number_and_title(self):
        hymn = HymnLyrics(
            number="ELW 335",
            title="Jesus, Keep Me Near the Cross",
            verses=[],
        )

        assert _hymn_title_str(hymn) == "ELW 335 - Jesus, Keep Me Near the Cross"

    def test_preserves_number_when_title_missing(self):
        hymn = HymnLyrics(number="ELW 335", title="", verses=[])

        assert _hymn_title_str(hymn) == "ELW 335"

    def test_appends_verse_label_after_title(self):
        hymn = HymnLyrics(
            number="ELW 386",
            title="O Sons and Daughters, Let Us Sing",
            verses=[],
            verse_label="Verses 1, 3-5",
        )

        assert (
            _hymn_title_str(hymn)
            == "ELW 386 - O Sons and Daughters, Let Us Sing (Verses 1, 3-5)"
        )


# ── Auto-adjust tests ────────────────────────────────────────────────


class TestBookletBlanks:
    @pytest.mark.parametrize("pages,expected", [
        (4, 0), (8, 0), (12, 0), (16, 0),   # multiples of 4
        (5, 3), (6, 2), (7, 1),              # need padding
        (13, 3), (14, 2), (15, 1),
        (1, 3), (2, 2), (3, 1),
    ])
    def test_known_values(self, pages, expected):
        assert _booklet_blanks(pages) == expected


class TestBestDirection:
    def test_13_pages_tighten(self):
        # 3 blanks: tighten_dist=1, loosen_dist=2 => tighten
        assert _best_direction(13) == "tighten"

    def test_14_pages_loosen(self):
        # 2 blanks: tighten_dist=2, loosen_dist=1 => loosen
        assert _best_direction(14) == "loosen"

    def test_15_pages_already_acceptable(self):
        # 1 blank — already acceptable, direction irrelevant => tighten
        assert _best_direction(15) == "tighten"

    def test_multiple_of_4_returns_tighten(self):
        # 0 blanks — already acceptable, direction irrelevant => tighten
        assert _best_direction(16) == "tighten"

    def test_9_pages_tighten(self):
        # 3 blanks: tighten_dist=1, loosen_dist=2 => tighten
        assert _best_direction(9) == "tighten"

    def test_11_pages_already_acceptable(self):
        # 1 blank — already acceptable, direction irrelevant => tighten
        assert _best_direction(11) == "tighten"

    def test_10_pages_loosen(self):
        # 2 blanks: tighten_dist=2, loosen_dist=1 => loosen
        assert _best_direction(10) == "loosen"

    def test_6_pages_loosen(self):
        # 2 blanks: tighten_dist=2, loosen_dist=1 => loosen
        assert _best_direction(6) == "loosen"

    def test_5_pages_tighten(self):
        # 3 blanks: tighten_dist=1, loosen_dist=2 => tighten
        assert _best_direction(5) == "tighten"


class TestTightenProfiles:
    def test_count(self):
        assert len(BULLETIN_TIGHTEN_PROFILES) == 6

    def test_names_ordered(self):
        names = [p.name for p in BULLETIN_TIGHTEN_PROFILES]
        assert names == ["T1", "T2", "T3", "T4", "T5", "T6"]

    def test_scales_in_bounds(self):
        for p in BULLETIN_TIGHTEN_PROFILES:
            assert 0.80 <= p.scale <= 1.10, f"{p.name} scale {p.scale} out of bounds"

    def test_scale_decreases_or_stays(self):
        scales = [p.scale for p in BULLETIN_TIGHTEN_PROFILES]
        for i in range(1, len(scales)):
            assert scales[i] <= scales[i - 1], (
                f"T{i+1} scale {scales[i]} > T{i} scale {scales[i-1]}"
            )

    def test_all_have_css(self):
        for p in BULLETIN_TIGHTEN_PROFILES:
            assert len(p.css) > 0, f"{p.name} has empty CSS"


class TestLoosenProfiles:
    def test_count(self):
        assert len(BULLETIN_LOOSEN_PROFILES) == 6

    def test_names_ordered(self):
        names = [p.name for p in BULLETIN_LOOSEN_PROFILES]
        assert names == ["L1", "L2", "L3", "L4", "L5", "L6"]

    def test_scales_in_bounds(self):
        for p in BULLETIN_LOOSEN_PROFILES:
            assert 0.80 <= p.scale <= 1.10, f"{p.name} scale {p.scale} out of bounds"

    def test_scale_increases_or_stays(self):
        scales = [p.scale for p in BULLETIN_LOOSEN_PROFILES]
        for i in range(1, len(scales)):
            assert scales[i] >= scales[i - 1], (
                f"L{i+1} scale {scales[i]} < L{i} scale {scales[i-1]}"
            )

    def test_all_have_css(self):
        for p in BULLETIN_LOOSEN_PROFILES:
            assert len(p.css) > 0, f"{p.name} has empty CSS"

    def test_profiles_do_not_force_cover_overflow(self):
        for p in BULLETIN_LOOSEN_PROFILES:
            assert "cover { min-height: 8" not in p.css


class TestInjectCss:
    def test_injects_before_closing_style(self):
        html = "<html><style>body { color: black; }</style><body></body></html>"
        result = _inject_css(html, ".spacer { height: 0pt; }")
        assert "/* auto-adjust */" in result
        assert ".spacer { height: 0pt; }" in result
        assert result.index(".spacer") < result.index("</style>")

    def test_preserves_original_css(self):
        html = "<html><style>body { color: black; }</style></html>"
        result = _inject_css(html, ".spacer { height: 4pt; }")
        assert "body { color: black; }" in result

    def test_no_style_tag_unchanged(self):
        html = "<html><body>Hello</body></html>"
        result = _inject_css(html, ".spacer { height: 0pt; }")
        # No </style> to replace, so html unchanged
        assert result == html


class TestAdjustProfileDataclass:
    def test_default_scale(self):
        p = AdjustProfile(name="test", css=".foo { bar: baz; }")
        assert p.scale == 1.0

    def test_custom_scale(self):
        p = AdjustProfile(name="test", css=".foo { bar: baz; }", scale=0.95)
        assert p.scale == 0.95


class TestFetchHymnImageUri:
    """_fetch_hymn_image_uri returns harmony notation URI or "" on failure."""

    def _hymn(self, number: str = "ELW 504") -> HymnLyrics:
        return HymnLyrics(number=number, title="A Mighty Fortress", verses=[])

    def test_no_client_returns_empty(self):
        assert _fetch_hymn_image_uri(None, self._hymn()) == ""

    def test_no_hymn_returns_empty(self):
        assert _fetch_hymn_image_uri(MagicMock(), None) == ""

    def test_malformed_number_returns_empty(self):
        result = _fetch_hymn_image_uri(MagicMock(), self._hymn(number="ELW"))
        assert result == ""

    @patch("bulletin_maker.renderer.html_renderer.fetch_hymn_image")
    @patch("bulletin_maker.renderer.html_renderer._image_to_data_uri")
    def test_success_prefers_harmony(self, mock_uri, mock_fetch):
        mock_fetch.return_value = "/tmp/x.jpg"
        mock_uri.return_value = "data:image/jpeg;base64,XXXX"

        result = _fetch_hymn_image_uri(MagicMock(), self._hymn())

        assert result == "data:image/jpeg;base64,XXXX"
        mock_fetch.assert_called_once()
        kwargs = mock_fetch.call_args.kwargs
        assert kwargs["collection"] == "ELW"
        assert kwargs["image_type"] == "harmony"

    @patch("bulletin_maker.renderer.html_renderer.fetch_hymn_image")
    @patch("bulletin_maker.renderer.html_renderer._image_to_data_uri")
    def test_falls_back_to_melody_when_harmony_fails(self, mock_uri, mock_fetch):
        mock_fetch.side_effect = [
            ContentNotFoundError("no harmony"),
            "/tmp/x.jpg",
        ]
        mock_uri.return_value = "data:image/jpeg;base64,YYYY"

        result = _fetch_hymn_image_uri(MagicMock(), self._hymn())

        assert result == "data:image/jpeg;base64,YYYY"
        assert mock_fetch.call_count == 2
        assert mock_fetch.call_args_list[0].kwargs["image_type"] == "harmony"
        assert mock_fetch.call_args_list[1].kwargs["image_type"] == "melody"

    @patch("bulletin_maker.renderer.html_renderer.fetch_hymn_image")
    def test_both_fetches_fail_returns_empty(self, mock_fetch):
        mock_fetch.side_effect = ContentNotFoundError("missing")
        assert _fetch_hymn_image_uri(MagicMock(), self._hymn()) == ""
        assert mock_fetch.call_count == 2

    @patch("bulletin_maker.renderer.html_renderer.fetch_hymn_image")
    def test_network_error_falls_through(self, mock_fetch):
        mock_fetch.side_effect = NetworkError("timeout")
        assert _fetch_hymn_image_uri(MagicMock(), self._hymn()) == ""

    @patch("bulletin_maker.renderer.html_renderer.fetch_hymn_image")
    def test_oserror_falls_through(self, mock_fetch):
        mock_fetch.side_effect = OSError("disk full")
        assert _fetch_hymn_image_uri(MagicMock(), self._hymn()) == ""


class TestLoadOffertoryImageUri:
    """_load_offertory_image_uri loads bundled asset, returns "" on missing."""

    def test_returns_data_uri_when_bundled(self):
        result = _load_offertory_image_uri()
        assert result.startswith("data:image/")
        assert ";base64," in result

    @patch("bulletin_maker.renderer.html_renderer.get_offertory_image")
    def test_returns_empty_when_missing(self, mock_get):
        mock_get.side_effect = FileNotFoundError("not bundled")
        assert _load_offertory_image_uri() == ""


class TestCanticleTextForConfig:
    """_canticle_text_for_config maps config.canticle to the right text dict."""

    @pytest.mark.parametrize("canticle, expected", [
        (CANTICLE_GLORY_TO_GOD, GLORY_TO_GOD_TEXT),
        (CANTICLE_THIS_IS_THE_FEAST, THIS_IS_THE_FEAST_TEXT),
        (CANTICLE_NONE, None),
        (None, None),
    ])
    def test_dispatch(self, canticle, expected):
        assert _canticle_text_for_config(_canticle_config(canticle)) is expected


class TestCanticleImageUriForConfig:
    """_canticle_image_uri_for_config maps config.canticle to a notation image URI."""

    @pytest.mark.parametrize("canticle", [CANTICLE_GLORY_TO_GOD, CANTICLE_THIS_IS_THE_FEAST])
    @patch("bulletin_maker.renderer.html_renderer._safe_setting_image_uri")
    def test_named_canticle_fetches_image(self, mock_safe, canticle):
        mock_safe.return_value = f"data:image/jpeg;base64,{canticle}"
        result = _canticle_image_uri_for_config(_canticle_config(canticle))
        assert result == f"data:image/jpeg;base64,{canticle}"
        mock_safe.assert_called_once_with(canticle, None, None)

    @pytest.mark.parametrize("canticle", [CANTICLE_NONE, None])
    @patch("bulletin_maker.renderer.html_renderer._safe_setting_image_uri")
    def test_none_or_unset_skips_fetch(self, mock_safe, canticle):
        assert _canticle_image_uri_for_config(_canticle_config(canticle)) == ""
        mock_safe.assert_not_called()
