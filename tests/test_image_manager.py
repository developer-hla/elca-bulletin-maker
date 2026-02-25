"""Tests for image_manager — asset lookup and path resolution."""

from __future__ import annotations

import pytest

from bulletin_maker.renderer.image_manager import (
    get_setting_image,
    get_gospel_acclamation_image,
    SETTING_TWO_DIR,
    GOSPEL_ACCLAMATION_DIR,
    _SETTING_TWO_ATOM_CODES,
    _GA_SEASON_MAP,
)
from bulletin_maker.renderer.season import LiturgicalSeason


class TestGetSettingImage:

    def test_valid_pieces_resolve(self):
        """All known pieces should resolve to an existing file (assets downloaded)."""
        for piece in _SETTING_TWO_ATOM_CODES:
            path = get_setting_image(piece)
            assert path.exists(), f"Missing asset: {path}"

    def test_invalid_piece_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown setting piece"):
            get_setting_image("nonexistent_piece")


class TestGetGospelAcclamationImage:

    def test_all_seasons_resolve(self):
        """Every season should map to an existing GA image."""
        for season in LiturgicalSeason:
            path = get_gospel_acclamation_image(season)
            assert path.exists(), f"Missing GA for {season}: {path}"

    def test_lent_gets_lenten_verse(self):
        path = get_gospel_acclamation_image(LiturgicalSeason.LENT)
        assert "lenten_verse" in path.stem

    def test_ordinary_gets_alleluia(self):
        path = get_gospel_acclamation_image(LiturgicalSeason.PENTECOST)
        assert "alleluia" in path.stem

    def test_advent_gets_advent(self):
        path = get_gospel_acclamation_image(LiturgicalSeason.ADVENT)
        assert "alleluia" in path.stem  # advent uses same melody
