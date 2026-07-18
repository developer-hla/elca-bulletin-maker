"""Tests for the liturgical setting abstraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bulletin_maker.exceptions import BulletinError
from bulletin_maker.renderer.image_manager import (
    _ga_dir,
    _setting_dir,
    ASSETS_DIR,
    get_setting_image,
)
from bulletin_maker.renderer.settings import (
    DEFAULT_SETTING_KEY,
    SETTINGS,
    USER_ASSETS_DIR,
    get_setting,
)


class TestSettingsRegistry:

    def test_five_elw_settings_registered(self):
        assert set(SETTINGS) == {
            "setting_one", "setting_two", "setting_three",
            "setting_four", "setting_five",
        }

    def test_default_is_setting_two(self):
        assert DEFAULT_SETTING_KEY == "setting_two"
        assert get_setting(DEFAULT_SETTING_KEY).bundled is True

    def test_only_setting_two_is_bundled(self):
        bundled = [s.key for s in SETTINGS.values() if s.bundled]
        assert bundled == ["setting_two"]

    def test_atom_prefixes_follow_verified_pattern(self):
        assert get_setting("setting_one").atom_prefix == "elw_hc1"
        assert get_setting("setting_five").atom_prefix == "elw_hc5"

    def test_unknown_setting_raises(self):
        with pytest.raises(BulletinError, match="Unknown liturgical setting"):
            get_setting("setting_ninety")


class TestAssetDirs:

    def test_bundled_setting_uses_package_assets(self):
        d = _setting_dir(get_setting("setting_two"))
        assert d == ASSETS_DIR / "setting_two"

    def test_unbundled_setting_uses_user_cache(self):
        d = _setting_dir(get_setting("setting_three"))
        assert d == USER_ASSETS_DIR / "setting_three"

    def test_unbundled_ga_dir_nested_under_setting(self):
        d = _ga_dir(get_setting("setting_three"))
        assert d == USER_ASSETS_DIR / "setting_three" / "gospel_acclamation"


class TestOnDemandDownload:

    def test_missing_asset_without_client_raises(self, tmp_path):
        setting = get_setting("setting_three")
        with patch("bulletin_maker.renderer.image_manager.USER_ASSETS_DIR", tmp_path), \
             patch("bulletin_maker.renderer.settings.USER_ASSETS_DIR", tmp_path):
            with pytest.raises(FileNotFoundError):
                get_setting_image("kyrie", setting=setting)

    def test_missing_asset_downloads_with_client(self, tmp_path):
        setting = get_setting("setting_three")
        client = MagicMock()
        client.download_image.return_value = b"\xff\xd8\xe0 fake jpeg"
        with patch("bulletin_maker.renderer.image_manager._setting_dir",
                   return_value=tmp_path / "setting_three"):
            path = get_setting_image("kyrie", setting=setting, client=client)
        assert path.exists()
        assert path.name == "kyrie.jpg"
        url = client.download_image.call_args.args[0]
        assert "atomCode=elw_hc3_kyrie_m" in url

    def test_download_cached_on_second_call(self, tmp_path):
        setting = get_setting("setting_three")
        client = MagicMock()
        client.download_image.return_value = b"\xff\xd8\xe0 fake jpeg"
        with patch("bulletin_maker.renderer.image_manager._setting_dir",
                   return_value=tmp_path / "setting_three"):
            get_setting_image("sanctus", setting=setting, client=client)
            get_setting_image("sanctus", setting=setting, client=client)
        assert client.download_image.call_count == 1


class TestPerSettingDifferences:

    def test_setting_three_ga_uses_alleluia_segment(self):
        from bulletin_maker.renderer.image_manager import _ga_atom_segment
        assert _ga_atom_segment(get_setting("setting_three"), "alleluia") == "alleluia"
        assert _ga_atom_segment(get_setting("setting_two"), "alleluia") == "accltext"

    def test_lenten_verse_segment_common_to_all(self):
        from bulletin_maker.renderer.image_manager import _ga_atom_segment
        for setting in SETTINGS.values():
            assert _ga_atom_segment(setting, "lenten_verse") == "lentaccl"

    def test_missing_piece_raises_content_not_found(self):
        from bulletin_maker.exceptions import ContentNotFoundError
        with pytest.raises(ContentNotFoundError, match="does not include"):
            get_setting_image("nunc_dimittis", setting=get_setting("setting_three"))

    def test_setting_five_lacks_feast_canticle(self):
        assert "this_is_the_feast" in get_setting("setting_five").missing_pieces
