"""Check GitHub releases for a newer version of Bulletin Maker."""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable, Optional

import httpx

from bulletin_maker.exceptions import UpdateError
from bulletin_maker.version import __version__

logger = logging.getLogger(__name__)

GITHUB_REPO = "developer-hla/elca-bulletin-maker"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

UPDATES_DIR = Path.home() / ".bulletin-maker" / "updates"


def _parse_version(tag: str) -> tuple[int, ...]:
    """Parse a version tag like 'v1.2.3' into (1, 2, 3)."""
    match = re.match(r"v?(\d+(?:\.\d+)*)", tag)
    if not match:
        return (0,)
    return tuple(int(x) for x in match.group(1).split("."))


def _pick_asset_url(assets: list[dict]) -> Optional[str]:
    """Pick the download URL for the current platform from release assets."""
    system = platform.system().lower()
    keyword = "macos" if system == "darwin" else "windows"

    for asset in assets:
        name = asset.get("name", "").lower()
        if keyword in name and name.endswith(".zip"):
            return asset.get("browser_download_url")
    return None


def check_for_update() -> Optional[dict]:
    """Check if a newer release is available on GitHub.

    Returns a dict with ``current``, ``latest``, ``download_url``, and
    ``release_notes`` keys when an update is available, or ``None`` if
    up-to-date (or on any error).
    """
    try:
        resp = httpx.get(
            RELEASES_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=5.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()

        tag = data.get("tag_name", "")
        latest = _parse_version(tag)
        current = _parse_version(__version__)

        if latest <= current:
            return None

        download_url = _pick_asset_url(data.get("assets", []))
        html_url = data.get("html_url", "")

        return {
            "current": __version__,
            "latest": tag.lstrip("v"),
            "download_url": download_url or html_url,
            "release_notes": data.get("body", ""),
        }
    except Exception:
        logger.debug("Update check failed", exc_info=True)
        return None


# ── Path Detection ────────────────────────────────────────────────────


def get_install_path() -> Optional[Path]:
    """Return the install root for the running frozen app.

    macOS: walk up from sys.executable to the .app bundle.
    Windows: sys.executable's parent directory.
    Returns None when not running as a frozen (PyInstaller) bundle.
    """
    if not getattr(sys, "frozen", False):
        return None

    exe = Path(sys.executable)
    system = platform.system()

    if system == "Darwin":
        # Walk up to find the .app bundle
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent
        return None
    elif system == "Windows":
        return exe.parent
    return None


def is_install_writable() -> bool:
    """Check whether the current install location can be replaced."""
    install = get_install_path()
    if install is None:
        return False
    return os.access(install.parent, os.W_OK)


# ── Download ──────────────────────────────────────────────────────────


def download_update(
    url: str,
    dest_dir: Path,
    progress_callback: Optional[Callable[[str, str, int], None]] = None,
) -> Path:
    """Download a release zip to *dest_dir*/update.zip.

    Calls *progress_callback(step, detail, pct)* with download progress
    scaled between 10 and 60.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / "update.zip"

    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(zip_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total:
                        pct = 10 + int(50 * downloaded / total)
                        mb = downloaded / (1024 * 1024)
                        progress_callback(
                            "update",
                            f"Downloading... {mb:.1f} MB",
                            min(pct, 60),
                        )
    except Exception as exc:
        # Clean up partial download
        if zip_path.exists():
            zip_path.unlink()
        raise UpdateError(f"Download failed: {exc}") from exc

    return zip_path


# ── Extract ───────────────────────────────────────────────────────────


def extract_update(zip_path: Path, staging_dir: Path) -> Path:
    """Extract a release zip and return the path to the payload.

    macOS: returns the path to the extracted .app bundle.
    Windows: returns the directory containing the extracted exe folder.
    Validates paths to prevent zip-slip (path traversal).
    """
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Validate all paths before extraction
            for info in zf.infolist():
                target = (staging_dir / info.filename).resolve()
                if not str(target).startswith(str(staging_dir.resolve())):
                    raise UpdateError(
                        f"Zip contains path traversal: {info.filename}"
                    )
            zf.extractall(staging_dir)
    except zipfile.BadZipFile as exc:
        raise UpdateError(f"Corrupt zip file: {exc}") from exc

    system = platform.system()

    if system == "Darwin":
        # Find the .app bundle in extracted contents
        for item in staging_dir.rglob("*.app"):
            if item.is_dir():
                return item
        raise UpdateError("No .app bundle found in update zip")
    else:
        # Windows: find the directory containing an exe
        for item in staging_dir.iterdir():
            if item.is_dir():
                exes = list(item.glob("*.exe"))
                if exes:
                    return item
        # Maybe the exe is at the top level
        exes = list(staging_dir.glob("*.exe"))
        if exes:
            return staging_dir
        raise UpdateError("No executable found in update zip")


# ── Replace + Relaunch ────────────────────────────────────────────────


def _backup_current(install_path: Path, backup_dir: Path) -> Path:
    """Move the current install to a backup location."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / install_path.name
    if backup_path.exists():
        shutil.rmtree(backup_path)
    shutil.move(str(install_path), str(backup_path))
    return backup_path


def _replace_macos(install_path: Path, staged_app: Path) -> None:
    """Replace the macOS .app bundle and re-sign."""
    # Remove old app, then move new app into place
    if install_path.exists():
        shutil.rmtree(install_path)
    shutil.move(str(staged_app), str(install_path))

    # Remove quarantine attribute
    subprocess.run(
        ["xattr", "-cr", str(install_path)],
        capture_output=True,
    )
    # Ad-hoc code sign
    subprocess.run(
        ["codesign", "--deep", "--force", "--sign", "-", str(install_path)],
        capture_output=True,
    )


def _replace_windows(install_path: Path, staged_dir: Path) -> Path:
    """Write a bat helper script that replaces the install after process exit."""
    bat_path = UPDATES_DIR / "update.bat"

    # Find the main exe name in the staged directory
    staged_exes = list(staged_dir.glob("*.exe"))
    exe_name = staged_exes[0].name if staged_exes else "Bulletin Maker.exe"

    bat_content = f'''@echo off
echo Waiting for Bulletin Maker to exit...
timeout /t 2 /nobreak >nul
robocopy "{staged_dir}" "{install_path}" /mir /njh /njs /ndl /nc /ns /nfl >nul
echo Starting updated Bulletin Maker...
start "" "{install_path / exe_name}"
del "%~f0"
'''
    bat_path.write_text(bat_content)
    return bat_path


def _relaunch_macos(install_path: Path) -> None:
    """Launch the new macOS .app and exit."""
    exe = install_path / "Contents" / "MacOS" / "Bulletin Maker"
    if not exe.exists():
        # Try to find any executable in the MacOS dir
        macos_dir = install_path / "Contents" / "MacOS"
        if macos_dir.exists():
            for item in macos_dir.iterdir():
                if item.is_file() and os.access(item, os.X_OK):
                    exe = item
                    break
    subprocess.Popen([str(exe)])
    sys.exit(0)


def _relaunch_windows(bat_path: Path) -> None:
    """Launch the bat helper and exit."""
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat_path)],
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
    )
    sys.exit(0)


# ── Orchestrator ──────────────────────────────────────────────────────


def install_update(
    download_url: str,
    progress_callback: Optional[Callable[[str, str, int], None]] = None,
) -> None:
    """Download, extract, replace, and relaunch the application.

    Raises UpdateError on any failure. Cleans up staging on error.
    """
    install_path = get_install_path()
    if install_path is None:
        raise UpdateError("Cannot determine install location (not a frozen app)")

    if not is_install_writable():
        raise UpdateError("Install location is not writable")

    staging_dir = UPDATES_DIR / "staging"
    backup_dir = UPDATES_DIR / "backup"

    try:
        # Download
        if progress_callback:
            progress_callback("update", "Downloading update...", 10)
        zip_path = download_update(download_url, UPDATES_DIR, progress_callback)

        # Extract
        if progress_callback:
            progress_callback("update", "Extracting update...", 65)
        staged_payload = extract_update(zip_path, staging_dir)

        # Backup current
        if progress_callback:
            progress_callback("update", "Backing up current version...", 75)
        _backup_current(install_path, backup_dir)

        # Replace
        if progress_callback:
            progress_callback("update", "Installing update...", 85)

        system = platform.system()
        if system == "Darwin":
            _replace_macos(install_path, staged_payload)
            if progress_callback:
                progress_callback("update", "Relaunching...", 95)
            _relaunch_macos(install_path)
        elif system == "Windows":
            bat_path = _replace_windows(install_path, staged_payload)
            if progress_callback:
                progress_callback("update", "Relaunching...", 95)
            _relaunch_windows(bat_path)
        else:
            raise UpdateError(f"Unsupported platform: {system}")

    except UpdateError:
        # Clean up staging but keep backup intact
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    except Exception as exc:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise UpdateError(f"Update failed: {exc}") from exc


# ── Cleanup ───────────────────────────────────────────────────────────


def cleanup_update_artifacts() -> None:
    """Remove leftover update files from a previous update.

    Called on app startup to clean up staging/backup dirs.
    """
    if UPDATES_DIR.exists():
        try:
            shutil.rmtree(UPDATES_DIR)
            logger.debug("Cleaned up update artifacts")
        except Exception:
            logger.debug("Could not clean update artifacts", exc_info=True)
