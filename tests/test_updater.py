"""Tests for the GitHub update checker and in-app updater."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from bulletin_maker.exceptions import UpdateError
from bulletin_maker.updater import (
    _parse_version,
    _pick_asset_url,
    check_for_update,
    cleanup_update_artifacts,
    download_update,
    extract_update,
    get_install_path,
    install_update,
    is_install_writable,
)


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
            "body": "Bug fixes and improvements",
            "assets": [],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = check_for_update()
        assert result is not None
        assert result["current"] == "0.1.0"
        assert result["latest"] == "0.2.0"
        assert result["release_notes"] == "Bug fixes and improvements"

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

    @patch("bulletin_maker.updater.httpx.get")
    @patch("bulletin_maker.updater.__version__", "0.1.0")
    def test_release_notes_empty_when_absent(self, mock_get):
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
        assert result["release_notes"] == ""


class TestGetInstallPath:
    def test_not_frozen(self):
        with patch("bulletin_maker.updater.sys") as mock_sys:
            mock_sys.frozen = False
            assert get_install_path() is None

    def test_no_frozen_attr(self):
        """When sys.frozen doesn't exist (normal Python)."""
        assert get_install_path() is None

    @patch("bulletin_maker.updater.platform.system", return_value="Darwin")
    def test_macos_app_bundle(self, _mock_sys):
        with patch("bulletin_maker.updater.sys") as mock_sys:
            mock_sys.frozen = True
            mock_sys.executable = "/Applications/Bulletin Maker.app/Contents/MacOS/Bulletin Maker"
            result = get_install_path()
            assert result == Path("/Applications/Bulletin Maker.app")

    @patch("bulletin_maker.updater.platform.system", return_value="Windows")
    def test_windows_exe(self, _mock_sys, tmp_path):
        exe_dir = tmp_path / "Bulletin Maker"
        exe_dir.mkdir()
        exe_path = exe_dir / "Bulletin Maker.exe"
        exe_path.write_bytes(b"MZ")

        with patch("bulletin_maker.updater.sys") as mock_sys:
            mock_sys.frozen = True
            mock_sys.executable = str(exe_path)
            result = get_install_path()
            assert result == exe_dir

    @patch("bulletin_maker.updater.platform.system", return_value="Darwin")
    def test_macos_no_app_suffix(self, _mock_sys):
        """If exe is not inside a .app bundle, returns None."""
        with patch("bulletin_maker.updater.sys") as mock_sys:
            mock_sys.frozen = True
            mock_sys.executable = "/usr/local/bin/bulletin-maker"
            result = get_install_path()
            assert result is None


class TestIsInstallWritable:
    def test_not_frozen_returns_false(self):
        assert is_install_writable() is False

    @patch("bulletin_maker.updater.get_install_path")
    @patch("bulletin_maker.updater.os.access", return_value=True)
    def test_writable(self, _mock_access, mock_path):
        mock_path.return_value = Path("/Applications/Bulletin Maker.app")
        assert is_install_writable() is True

    @patch("bulletin_maker.updater.get_install_path")
    @patch("bulletin_maker.updater.os.access", return_value=False)
    def test_read_only(self, _mock_access, mock_path):
        mock_path.return_value = Path("/Applications/Bulletin Maker.app")
        assert is_install_writable() is False


class TestDownloadUpdate:
    def test_success(self, tmp_path):
        content = b"fake zip content" * 100
        mock_response = MagicMock()
        mock_response.headers = {"content-length": str(len(content))}
        mock_response.iter_bytes.return_value = [content]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.raise_for_status = MagicMock()

        with patch("bulletin_maker.updater.httpx.stream", return_value=mock_response):
            result = download_update("https://example.com/update.zip", tmp_path)

        assert result == tmp_path / "update.zip"
        assert result.exists()
        assert result.read_bytes() == content

    def test_failure_cleans_up(self, tmp_path):
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.raise_for_status.side_effect = Exception("404")

        with patch("bulletin_maker.updater.httpx.stream", return_value=mock_response):
            with pytest.raises(UpdateError, match="Download failed"):
                download_update("https://example.com/bad.zip", tmp_path)

        assert not (tmp_path / "update.zip").exists()

    def test_progress_callbacks(self, tmp_path):
        content = b"x" * 65536
        mock_response = MagicMock()
        mock_response.headers = {"content-length": str(len(content))}
        mock_response.iter_bytes.return_value = [content]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.raise_for_status = MagicMock()

        callback = MagicMock()

        with patch("bulletin_maker.updater.httpx.stream", return_value=mock_response):
            download_update("https://example.com/update.zip", tmp_path, callback)

        callback.assert_called()
        # Check that the callback was called with "update" step
        assert callback.call_args[0][0] == "update"


class TestExtractUpdate:
    def _make_zip(self, tmp_path: Path, contents: dict[str, bytes]) -> Path:
        """Helper to create a zip with given file paths and contents."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for name, data in contents.items():
                zf.writestr(name, data)
        return zip_path

    def test_macos_app_bundle(self, tmp_path):
        zip_path = self._make_zip(tmp_path, {
            "Bulletin Maker.app/Contents/Info.plist": b"<plist/>",
            "Bulletin Maker.app/Contents/MacOS/Bulletin Maker": b"#!/bin/sh",
        })
        staging = tmp_path / "staging"

        with patch("bulletin_maker.updater.platform.system", return_value="Darwin"):
            result = extract_update(zip_path, staging)

        assert result.name == "Bulletin Maker.app"
        assert result.is_dir()

    def test_windows_exe_dir(self, tmp_path):
        zip_path = self._make_zip(tmp_path, {
            "Bulletin Maker/Bulletin Maker.exe": b"MZ...",
            "Bulletin Maker/python39.dll": b"dll",
        })
        staging = tmp_path / "staging"

        with patch("bulletin_maker.updater.platform.system", return_value="Windows"):
            result = extract_update(zip_path, staging)

        assert result.name == "Bulletin Maker"

    def test_path_traversal_rejected(self, tmp_path):
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../etc/passwd", "root:x:0:0")
        staging = tmp_path / "staging"

        with pytest.raises(UpdateError, match="path traversal"):
            extract_update(zip_path, staging)

    def test_no_app_found_macos(self, tmp_path):
        zip_path = self._make_zip(tmp_path, {
            "readme.txt": b"hello",
        })
        staging = tmp_path / "staging"

        with patch("bulletin_maker.updater.platform.system", return_value="Darwin"):
            with pytest.raises(UpdateError, match="No .app bundle"):
                extract_update(zip_path, staging)

    def test_no_exe_found_windows(self, tmp_path):
        zip_path = self._make_zip(tmp_path, {
            "readme.txt": b"hello",
        })
        staging = tmp_path / "staging"

        with patch("bulletin_maker.updater.platform.system", return_value="Windows"):
            with pytest.raises(UpdateError, match="No executable"):
                extract_update(zip_path, staging)


class TestReplaceMacos:
    def test_old_removed_new_moved(self, tmp_path):
        from bulletin_maker.updater import _replace_macos

        install_path = tmp_path / "Test.app"
        install_path.mkdir()
        (install_path / "old_file").write_text("old")

        staged_app = tmp_path / "staging" / "Test.app"
        staged_app.mkdir(parents=True)
        (staged_app / "new_file").write_text("new")

        with patch("bulletin_maker.updater.subprocess.run") as mock_run:
            _replace_macos(install_path, staged_app)

        # Old was replaced with new
        assert (install_path / "new_file").read_text() == "new"
        assert not (install_path / "old_file").exists()
        assert not staged_app.exists()

        # xattr and codesign were called
        assert mock_run.call_count == 2
        xattr_call = mock_run.call_args_list[0]
        assert "xattr" in xattr_call[0][0]
        codesign_call = mock_run.call_args_list[1]
        assert "codesign" in codesign_call[0][0]


class TestReplaceWindows:
    def test_bat_script_content(self, tmp_path):
        from bulletin_maker.updater import _replace_windows

        install_path = tmp_path / "Bulletin Maker"
        install_path.mkdir()
        staged_dir = tmp_path / "staging" / "Bulletin Maker"
        staged_dir.mkdir(parents=True)
        (staged_dir / "Bulletin Maker.exe").write_bytes(b"MZ")

        with patch("bulletin_maker.updater.UPDATES_DIR", tmp_path / "updates"):
            (tmp_path / "updates").mkdir(parents=True, exist_ok=True)
            bat_path = _replace_windows(install_path, staged_dir)

        assert bat_path.exists()
        content = bat_path.read_text()
        assert "robocopy" in content
        assert "Bulletin Maker.exe" in content
        assert str(install_path) in content


class TestInstallUpdate:
    @patch("bulletin_maker.updater.get_install_path", return_value=None)
    def test_no_install_path_raises(self, _mock):
        with pytest.raises(UpdateError, match="not a frozen app"):
            install_update("https://example.com/update.zip")

    @patch("bulletin_maker.updater.get_install_path")
    @patch("bulletin_maker.updater.is_install_writable", return_value=False)
    def test_readonly_raises(self, _mock_w, mock_path):
        mock_path.return_value = Path("/Applications/Test.app")
        with pytest.raises(UpdateError, match="not writable"):
            install_update("https://example.com/update.zip")

    @patch("bulletin_maker.updater._relaunch_macos")
    @patch("bulletin_maker.updater._replace_macos")
    @patch("bulletin_maker.updater._backup_current")
    @patch("bulletin_maker.updater.extract_update")
    @patch("bulletin_maker.updater.download_update")
    @patch("bulletin_maker.updater.is_install_writable", return_value=True)
    @patch("bulletin_maker.updater.get_install_path")
    @patch("bulletin_maker.updater.platform.system", return_value="Darwin")
    def test_full_flow_macos(self, _sys, mock_path, _writable,
                             mock_dl, mock_extract, mock_backup,
                             mock_replace, mock_relaunch):
        mock_path.return_value = Path("/Applications/Test.app")
        mock_dl.return_value = Path("/tmp/update.zip")
        mock_extract.return_value = Path("/tmp/staging/Test.app")
        mock_backup.return_value = Path("/tmp/backup/Test.app")

        callback = MagicMock()

        with patch("bulletin_maker.updater.UPDATES_DIR", Path("/tmp/updates")):
            install_update("https://example.com/update.zip", callback)

        mock_dl.assert_called_once()
        mock_extract.assert_called_once()
        mock_backup.assert_called_once()
        mock_replace.assert_called_once()
        mock_relaunch.assert_called_once()
        callback.assert_called()


class TestCleanupUpdateArtifacts:
    def test_removes_dir(self, tmp_path):
        updates_dir = tmp_path / "updates"
        updates_dir.mkdir()
        (updates_dir / "update.zip").write_bytes(b"data")
        (updates_dir / "staging").mkdir()

        with patch("bulletin_maker.updater.UPDATES_DIR", updates_dir):
            cleanup_update_artifacts()

        assert not updates_dir.exists()

    def test_noop_when_absent(self, tmp_path):
        updates_dir = tmp_path / "updates"

        with patch("bulletin_maker.updater.UPDATES_DIR", updates_dir):
            cleanup_update_artifacts()  # Should not raise

        assert not updates_dir.exists()
