"""Validation tests for static liturgical texts.

Ensures formatting consistency: stanza breaks, endings, unicode,
and structural invariants in hardcoded liturgical content.
"""

from __future__ import annotations

import pytest

from bulletin_maker.renderer.static_text import (
    AARONIC_BLESSING,
    AGNUS_DEI,
    APOSTLES_CREED,
    CHURCH_ADDRESS,
    CHURCH_NAME,
    CONFESSION_AND_FORGIVENESS,
    DISMISSAL,
    EUCHARISTIC_PRAYER_CLOSING,
    EUCHARISTIC_PRAYER_EXTENDED,
    GREAT_THANKSGIVING_DIALOG,
    GREAT_THANKSGIVING_PREFACE,
    INVITATION_TO_LENT,
    LORDS_PRAYER,
    MEMORIAL_ACCLAMATION,
    NICENE_CREED,
    NUNC_DIMITTIS,
    OFFERTORY_HYMN_VERSES,
    PRAYERS_INTRO,
    SANCTUS,
    STANDING_INSTRUCTIONS,
    WELCOME_MESSAGE,
    WORDS_OF_INSTITUTION,
)


class TestCreeds:
    def test_nicene_ends_with_amen(self):
        assert NICENE_CREED.strip().endswith("Amen.")

    def test_apostles_ends_with_amen(self):
        assert APOSTLES_CREED.strip().endswith("Amen.")

    def test_nicene_has_stanza_breaks(self):
        assert "\n\n" in NICENE_CREED

    def test_apostles_has_stanza_breaks(self):
        assert "\n\n" in APOSTLES_CREED

    def test_nicene_starts_we_believe(self):
        assert NICENE_CREED.startswith("We believe")

    def test_apostles_starts_i_believe(self):
        assert APOSTLES_CREED.startswith("I believe")


class TestLordsPrayer:
    def test_ends_with_amen(self):
        assert LORDS_PRAYER.strip().endswith("Amen.")

    def test_has_stanza_breaks(self):
        assert "\n\n" in LORDS_PRAYER

    def test_starts_our_father(self):
        assert LORDS_PRAYER.startswith("Our Father")


class TestLiturgicalTexts:
    def test_sanctus_has_stanza_breaks(self):
        assert "\n\n" in SANCTUS

    def test_sanctus_starts_holy(self):
        assert SANCTUS.startswith("Holy, holy, holy")

    def test_agnus_dei_has_three_petitions(self):
        # Three "Lamb of God" invocations
        assert AGNUS_DEI.count("Lamb of God") == 3

    def test_agnus_dei_ends_grant_us_peace(self):
        assert AGNUS_DEI.strip().endswith("grant us peace.")

    def test_nunc_dimittis_ends_with_amen(self):
        assert NUNC_DIMITTIS.strip().endswith("Amen.")

    def test_memorial_acclamation_three_lines(self):
        lines = [l for l in MEMORIAL_ACCLAMATION.split("\n") if l.strip()]
        assert len(lines) == 3

    def test_eucharistic_prayer_extended_nonempty(self):
        assert len(EUCHARISTIC_PRAYER_EXTENDED) > 100

    def test_eucharistic_prayer_closing_nonempty(self):
        assert len(EUCHARISTIC_PRAYER_CLOSING) > 100

    def test_words_of_institution_has_stanza_breaks(self):
        assert "\n\n" in WORDS_OF_INSTITUTION


class TestGreatThanksgiving:
    def test_dialog_has_six_exchanges(self):
        assert len(GREAT_THANKSGIVING_DIALOG) == 6

    def test_dialog_alternates_p_and_c(self):
        roles = [role for role, _ in GREAT_THANKSGIVING_DIALOG]
        assert roles == ["P", "C", "P", "C", "P", "C"]

    def test_preface_nonempty(self):
        assert len(GREAT_THANKSGIVING_PREFACE) > 50


class TestOffertoryHymn:
    def test_has_two_verses(self):
        assert len(OFFERTORY_HYMN_VERSES) == 2

    def test_verses_have_tab_separator(self):
        for verse in OFFERTORY_HYMN_VERSES:
            assert "\t" in verse, f"Verse missing tab separator: {verse[:30]}..."

    def test_verse_numbers(self):
        assert OFFERTORY_HYMN_VERSES[0].startswith("1\t")
        assert OFFERTORY_HYMN_VERSES[1].startswith("2\t")

    def test_verses_end_with_amen(self):
        for verse in OFFERTORY_HYMN_VERSES:
            assert verse.strip().endswith("Amen.")


class TestConfession:
    def test_is_list(self):
        assert isinstance(CONFESSION_AND_FORGIVENESS, list)

    def test_has_entries(self):
        assert len(CONFESSION_AND_FORGIVENESS) >= 5

    def test_entries_are_tuples(self):
        for entry in CONFESSION_AND_FORGIVENESS:
            assert isinstance(entry, tuple)
            assert len(entry) == 3

    def test_congregation_response_is_bold(self):
        # The "C" (congregation) entry should be bold
        c_entries = [e for e in CONFESSION_AND_FORGIVENESS if e[0] == "C"]
        assert len(c_entries) >= 1
        for entry in c_entries:
            assert entry[2] is True, "Congregation text should be bold"


class TestChurchInfo:
    def test_church_name(self):
        assert "Ascension" in CHURCH_NAME
        assert "Lutheran" in CHURCH_NAME

    def test_church_address_has_phone(self):
        assert "601" in CHURCH_ADDRESS

    def test_church_address_has_url(self):
        assert "ascensionlutheran.com" in CHURCH_ADDRESS


class TestMiscTexts:
    def test_dismissal_has_response(self):
        assert "Thanks be to God" in DISMISSAL

    def test_prayers_intro_nonempty(self):
        assert len(PRAYERS_INTRO) > 10

    def test_welcome_message_nonempty(self):
        assert len(WELCOME_MESSAGE) > 20

    def test_standing_instructions_nonempty(self):
        assert len(STANDING_INSTRUCTIONS) > 10

    def test_invitation_to_lent_nonempty(self):
        assert len(INVITATION_TO_LENT) > 100

    def test_aaronic_blessing_has_three_lines(self):
        lines = [l for l in AARONIC_BLESSING.split("\n") if l.strip()]
        assert len(lines) == 3

    def test_aaronic_blessing_has_cross_symbol(self):
        assert "\u2629" in AARONIC_BLESSING
