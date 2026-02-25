"""Tests for liturgical season detection and configuration."""

from __future__ import annotations

import pytest

from bulletin_maker.renderer.season import (
    LiturgicalSeason,
    detect_season,
    get_seasonal_config,
)


class TestDetectSeason:
    """detect_season() maps S&S titles to the correct liturgical season."""

    @pytest.mark.parametrize("title,expected", [
        ("First Sunday of Advent, Year A", LiturgicalSeason.ADVENT),
        ("Second Sunday of Advent, Year B", LiturgicalSeason.ADVENT),
        ("Christmas Day", LiturgicalSeason.CHRISTMAS),
        ("Christmas Eve", LiturgicalSeason.CHRISTMAS_EVE),
        ("Baptism of Our Lord", LiturgicalSeason.EPIPHANY),
        ("Third Sunday after Epiphany, Year C", LiturgicalSeason.EPIPHANY),
        ("Transfiguration of Our Lord", LiturgicalSeason.EPIPHANY),
        ("First Sunday in Lent, Year A", LiturgicalSeason.LENT),
        ("Ash Wednesday", LiturgicalSeason.LENT),
        ("Resurrection of Our Lord - Easter Day", LiturgicalSeason.EASTER),
        ("Sixth Sunday of Easter, Year B", LiturgicalSeason.EASTER),
        ("Day of Pentecost", LiturgicalSeason.PENTECOST),
        ("Lectionary 32, Year C", LiturgicalSeason.PENTECOST),
    ])
    def test_known_titles(self, title, expected):
        assert detect_season(title) == expected

    def test_unknown_defaults_to_pentecost(self):
        assert detect_season("Some Unknown Day") == LiturgicalSeason.PENTECOST

    def test_case_insensitive(self):
        assert detect_season("FIRST SUNDAY IN LENT") == LiturgicalSeason.LENT

    def test_full_sns_title_format(self):
        """S&S titles include the date prefix."""
        title = "Sunday, February 22, 2026 First Sunday in Lent, Year A"
        assert detect_season(title) == LiturgicalSeason.LENT


class TestGetSeasonalConfig:
    """get_seasonal_config() returns correct liturgical settings per season."""

    def test_lent_has_no_canticle(self):
        config = get_seasonal_config(LiturgicalSeason.LENT)
        assert config.canticle == "none"

    def test_lent_uses_nicene_creed(self):
        config = get_seasonal_config(LiturgicalSeason.LENT)
        assert config.creed_default == "nicene"

    def test_pentecost_uses_short_eucharistic(self):
        config = get_seasonal_config(LiturgicalSeason.PENTECOST)
        assert config.eucharistic_form == "short"

    def test_christmas_has_memorial_acclamation(self):
        config = get_seasonal_config(LiturgicalSeason.CHRISTMAS)
        assert config.has_memorial_acclamation is True

    def test_christmas_eve_no_kyrie(self):
        config = get_seasonal_config(LiturgicalSeason.CHRISTMAS_EVE)
        assert config.has_kyrie is False

    def test_all_seasons_have_config(self):
        for season in LiturgicalSeason:
            config = get_seasonal_config(season)
            assert config is not None
