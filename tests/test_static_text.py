"""Validation tests for static liturgical texts.

Ensures formatting consistency: stanza breaks, endings, unicode,
and structural invariants in hardcoded liturgical content.
"""

from __future__ import annotations

import pytest

from bulletin_maker.renderer.text_utils import DialogRole
from bulletin_maker.renderer.static_text import (
    AARONIC_BLESSING,
    AGNUS_DEI,
    APOSTLES_CREED,
    BAPTISM_FLOOD_PRAYER,
    BAPTISM_FORMULA,
    BAPTISM_PRESENTATION,
    BAPTISM_PROFESSION,
    BAPTISM_RENUNCIATION,
    BAPTISM_WELCOME,
    BAPTISM_WELCOME_RESPONSE,
    CONFESSION_AND_FORGIVENESS,
    DISMISSAL,
    EUCHARISTIC_PRAYER_CLOSING,
    EUCHARISTIC_PRAYER_EXTENDED,
    GLORY_TO_GOD_TEXT,
    GREAT_THANKSGIVING_DIALOG,
    GREAT_THANKSGIVING_PREFACE,
    GREETING,
    INVITATION_TO_COMMUNION,
    INVITATION_TO_LENT,
    KYRIE_DIALOG,
    LORDS_PRAYER,
    MEMORIAL_ACCLAMATION,
    NICENE_CREED,
    NUNC_DIMITTIS,
    OFFERTORY_HYMN_VERSES,
    PRAYERS_INTRO,
    SANCTUS,
    THIS_IS_THE_FEAST_TEXT,
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

    def test_words_of_institution_uses_handed_over(self):
        assert "In the night in which he was handed over" in WORDS_OF_INSTITUTION
        assert "In the night in which he was betrayed" not in WORDS_OF_INSTITUTION


class TestGreatThanksgiving:
    def test_dialog_has_six_exchanges(self):
        assert len(GREAT_THANKSGIVING_DIALOG) == 6

    def test_dialog_alternates_p_and_c(self):
        roles = [role for role, _ in GREAT_THANKSGIVING_DIALOG]
        P, C = DialogRole.PASTOR, DialogRole.CONGREGATION
        assert roles == [P, C, P, C, P, C]

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

    def test_no_amen_in_verses(self):
        for verse in OFFERTORY_HYMN_VERSES:
            assert "Amen" not in verse

    def test_verse_one_canonical_text(self):
        v1 = OFFERTORY_HYMN_VERSES[0]
        assert "Oh, come, Lord Jesus" in v1
        assert "be our guest" in v1
        assert "in your sight" in v1
        assert "be our joy" in v1
        assert v1.strip().endswith("delight.")

    def test_verse_two_canonical_text(self):
        v2 = OFFERTORY_HYMN_VERSES[1]
        assert "goodly share" in v2
        assert v2.strip().endswith("every table everywhere.")


class TestConfession:
    def test_is_list(self):
        assert isinstance(CONFESSION_AND_FORGIVENESS, list)

    def test_has_entries(self):
        assert len(CONFESSION_AND_FORGIVENESS) >= 5

    def test_entries_are_2_tuples(self):
        for entry in CONFESSION_AND_FORGIVENESS:
            assert isinstance(entry, tuple)
            assert len(entry) == 2

    def test_has_congregation_entry(self):
        c_entries = [e for e in CONFESSION_AND_FORGIVENESS
                     if e[0] is DialogRole.CONGREGATION]
        assert len(c_entries) >= 1

    def test_roles_are_dialog_role(self):
        for role, _ in CONFESSION_AND_FORGIVENESS:
            assert isinstance(role, DialogRole)


class TestMiscTexts:
    def test_dismissal_has_response(self):
        assert "Thanks be to God" in DISMISSAL

    def test_prayers_intro_nonempty(self):
        assert len(PRAYERS_INTRO) > 10

    def test_invitation_to_lent_nonempty(self):
        assert len(INVITATION_TO_LENT) > 100

    def test_invitation_to_communion_uses_ascension_text(self):
        assert "breathed your first breath" in INVITATION_TO_COMMUNION
        assert "breathe your last" in INVITATION_TO_COMMUNION
        assert "God\u2019s Table" in INVITATION_TO_COMMUNION
        assert INVITATION_TO_COMMUNION.endswith("Taste and see that the Lord is good.")

    def test_aaronic_blessing_has_three_lines(self):
        lines = [l for l in AARONIC_BLESSING.split("\n") if l.strip()]
        assert len(lines) == 3

    def test_aaronic_blessing_has_cross_symbol(self):
        assert "\u2629" in AARONIC_BLESSING


class TestBaptismTexts:
    def test_presentation_nonempty(self):
        assert len(BAPTISM_PRESENTATION) > 50

    def test_flood_prayer_nonempty(self):
        assert len(BAPTISM_FLOOD_PRAYER) > 100

    def test_renunciation_has_three_exchanges(self):
        # Three renunciation questions + three responses = 6 entries
        assert len(BAPTISM_RENUNCIATION) == 6

    def test_renunciation_entries_are_tuples(self):
        for entry in BAPTISM_RENUNCIATION:
            assert isinstance(entry, tuple)
            assert len(entry) == 2

    def test_renunciation_has_congregation_responses(self):
        c_entries = [e for e in BAPTISM_RENUNCIATION
                     if e[0] is DialogRole.CONGREGATION]
        assert len(c_entries) == 3

    def test_profession_has_three_exchanges(self):
        # Three belief questions + three responses = 6 entries
        assert len(BAPTISM_PROFESSION) == 6

    def test_profession_entries_are_tuples(self):
        for entry in BAPTISM_PROFESSION:
            assert isinstance(entry, tuple)
            assert len(entry) == 2

    def test_profession_has_apostles_creed_content(self):
        # The congregation responses contain the Apostles' Creed in Q&A form
        all_text = " ".join(t for _, t in BAPTISM_PROFESSION)
        assert "Father almighty" in all_text
        assert "Jesus Christ" in all_text
        assert "Holy Spirit" in all_text

    def test_formula_has_name_placeholder(self):
        assert "{name}" in BAPTISM_FORMULA

    def test_formula_formats_correctly(self):
        result = BAPTISM_FORMULA.format(name="John")
        assert "John" in result
        assert "baptize" in result

    def test_welcome_nonempty(self):
        assert len(BAPTISM_WELCOME) > 10

    def test_welcome_response_nonempty(self):
        assert len(BAPTISM_WELCOME_RESPONSE) > 50


class TestGreeting:
    def test_has_two_entries(self):
        assert len(GREETING) == 2

    def test_pastor_then_congregation(self):
        roles = [role for role, _ in GREETING]
        assert roles == [DialogRole.PASTOR, DialogRole.CONGREGATION]

    def test_pastor_text_canonical(self):
        pastor_text = GREETING[0][1]
        assert "grace of our Lord Jesus Christ" in pastor_text
        assert "love of God" in pastor_text
        assert "communion of the Holy Spirit" in pastor_text

    def test_congregation_response(self):
        assert GREETING[1][1] == "And also with you."


class TestKyrieDialog:
    def test_has_ten_entries(self):
        # Five exchanges: 5 P + 5 C
        assert len(KYRIE_DIALOG) == 10

    def test_alternates_p_and_c(self):
        roles = [role for role, _ in KYRIE_DIALOG]
        P, C = DialogRole.PASTOR, DialogRole.CONGREGATION
        assert roles == [P, C, P, C, P, C, P, C, P, C]

    def test_first_petition(self):
        assert "In peace, let us pray to the Lord." == KYRIE_DIALOG[0][1]

    def test_lord_have_mercy_responses(self):
        c_responses = [t for r, t in KYRIE_DIALOG if r is DialogRole.CONGREGATION]
        # First four responses are "Lord, have mercy.", last is "Amen."
        assert c_responses[:4] == ["Lord, have mercy."] * 4
        assert c_responses[4] == "Amen."

    def test_final_petition(self):
        assert "Help, save, comfort, and defend us, gracious Lord." == KYRIE_DIALOG[8][1]


class TestCanticleTexts:
    def test_glory_to_god_has_three_verses(self):
        assert len(GLORY_TO_GOD_TEXT["verses"]) == 3

    def test_glory_to_god_no_final_refrain(self):
        assert GLORY_TO_GOD_TEXT["final_refrain"] is None

    def test_glory_to_god_refrain_text(self):
        assert "Glory to God in the highest" in GLORY_TO_GOD_TEXT["refrain"]

    def test_glory_to_god_verse_one_starts_lord_god(self):
        assert GLORY_TO_GOD_TEXT["verses"][0].startswith("Lord God, heavenly King")

    def test_glory_to_god_verse_three_ends_amen(self):
        assert GLORY_TO_GOD_TEXT["verses"][2].rstrip().endswith("Amen.")

    def test_this_is_the_feast_has_two_verses(self):
        assert len(THIS_IS_THE_FEAST_TEXT["verses"]) == 2

    def test_this_is_the_feast_has_final_refrain(self):
        assert THIS_IS_THE_FEAST_TEXT["final_refrain"] is not None

    def test_this_is_the_feast_refrain_has_alleluia(self):
        assert "Alleluia" in THIS_IS_THE_FEAST_TEXT["refrain"]

    def test_this_is_the_feast_final_refrain_mentions_reign(self):
        assert "begun his reign" in THIS_IS_THE_FEAST_TEXT["final_refrain"]

    def test_this_is_the_feast_verse_two_ends_amen(self):
        assert THIS_IS_THE_FEAST_TEXT["verses"][1].rstrip().endswith("Amen.")

    @pytest.mark.parametrize("canticle", [GLORY_TO_GOD_TEXT, THIS_IS_THE_FEAST_TEXT])
    def test_canticle_has_required_keys(self, canticle):
        assert set(canticle.keys()) == {"refrain", "verses", "final_refrain"}

    @pytest.mark.parametrize("canticle", [GLORY_TO_GOD_TEXT, THIS_IS_THE_FEAST_TEXT])
    def test_canticle_verses_are_strings(self, canticle):
        for verse in canticle["verses"]:
            assert isinstance(verse, str)
            assert len(verse) > 20
