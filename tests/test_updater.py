"""Tests for the GitHub update checker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bulletin_maker.updater import _parse_version, _pick_asset_url, check_for_update


class TestParseVersion:
    def test_standard_tag(self):
        assert _parse_version("v1.2.3") == (1, 2, 3)

    def test_no_prefix(self):
        assert _parse_version("0.2.0") == (0, 2, 0)

    def test_two_part(self):
        assert _parse_version("v2.0") == (2, 0)

    def test_invalid(self):
        assert _parse_version("invalid") == (0,)


class TestPickAssetUrl:
    def test_macos_asset(self):
        assets = [
            {"name": "Bulletin-Maker-macos.zip", "browser_download_url": "https://example.com/mac.zip"},
            {"name": "Bulletin-Maker-windows.zip", "browser_download_url": "https://example.com/win.zip"},
        ]
        with patch("bulletin_maker.updater.platform") as mock_plat:
            mock_plat.system.return_value = "Darwin"
            assert _pick_asset_url(assets) == "https://example.com/mac.zip"

    def test_windows_asset(self):
        assets = [
            {"name": "Bulletin-Maker-macos.zip", "browser_download_url": "https://example.com/mac.zip"},
            {"name": "Bulletin-Maker-windows.zip", "browser_download_url": "https://example.com/win.zip"},
        ]
        with patch("bulletin_maker.updater.platform") as mock_plat:
            mock_plat.system.return_value = "Windows"
            assert _pick_asset_url(assets) == "https://example.com/win.zip"

    def test_no_matching_asset(self):
        assets = [{"name": "source.tar.gz", "browser_download_url": "https://example.com/src.tar.gz"}]
        assert _pick_asset_url(assets) is None


class TestCheckForUpdate:
    @patch("bulletin_maker.updater.httpx.get")
    @patch("bulletin_maker.updater.__version__", "0.1.0")
    def test_newer_version_available(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/test/releases/v0.2.0",
            "assets": [],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = check_for_update()
        assert result is not None
        assert result["current"] == "0.1.0"
        assert result["latest"] == "0.2.0"

    @patch("bulletin_maker.updater.httpx.get")
    @patch("bulletin_maker.updater.__version__", "0.2.0")
    def test_same_version(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/test/releases/v0.2.0",
            "assets": [],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        assert check_for_update() is None

    @patch("bulletin_maker.updater.httpx.get")
    @patch("bulletin_maker.updater.__version__", "0.3.0")
    def test_older_remote_version(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/test/releases/v0.2.0",
            "assets": [],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        assert check_for_update() is None

    @patch("bulletin_maker.updater.httpx.get")
    def test_network_error_returns_none(self, mock_get):
        mock_get.side_effect = Exception("Connection failed")
        assert check_for_update() is None

    @patch("bulletin_maker.updater.httpx.get")
    def test_timeout_returns_none(self, mock_get):
        import httpx
        mock_get.side_effect = httpx.TimeoutException("timed out")
        assert check_for_update() is None
