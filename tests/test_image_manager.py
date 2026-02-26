"""Tests for image_manager — asset lookup and path resolution."""

from __future__ import annotations

import pytest

from bulletin_maker.renderer.image_manager import (
    get_setting_image,
    get_gospel_acclamation_image,
    get_preface_image,
    load_asset_catalog,
    SETTING_TWO_DIR,
    GOSPEL_ACCLAMATION_DIR,
    _SETTING_TWO_ATOM_CODES,
    _GA_SEASON_MAP,
)
from bulletin_maker.renderer.season import (
    LiturgicalSeason,
    PrefaceType,
    get_preface_options,
)


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


class TestGetPrefaceImage:

    def test_all_preface_types_resolve(self):
        """Every PrefaceType member should resolve to an existing file."""
        for preface in PrefaceType:
            path = get_preface_image(preface)
            assert path.exists(), f"Missing preface: {preface}"

    def test_lent_returns_lent_image(self):
        path = get_preface_image(PrefaceType.LENT)
        assert "preface_lent" in path.stem

    def test_sundays_returns_sundays_image(self):
        path = get_preface_image(PrefaceType.SUNDAYS)
        assert "preface_sundays" in path.stem


class TestAssetCatalog:

    def test_load_asset_catalog_returns_dict(self):
        catalog = load_asset_catalog()
        assert "gospel_acclamation" in catalog
        assert "setting_pieces" in catalog
        assert "sung_liturgy" in catalog

    def test_preface_options_has_groups(self):
        options = get_preface_options()
        assert "seasonal" in options
        assert "occasional" in options
        assert len(options["seasonal"]) >= 7
        assert len(options["occasional"]) >= 10

    def test_preface_options_keys_match_files(self):
        """Every key in the catalog should have a matching PrefaceType and image."""
        options = get_preface_options()
        for group in ("seasonal", "occasional"):
            for item in options[group]:
                preface = PrefaceType(item["key"])
                path = get_preface_image(preface)
                assert path.exists(), f"Missing image for preface: {preface}"
