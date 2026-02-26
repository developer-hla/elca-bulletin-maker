"""Check GitHub releases for a newer version of Bulletin Maker."""

from __future__ import annotations

import logging
import platform
import re
from typing import Optional

import httpx

from bulletin_maker.version import __version__

logger = logging.getLogger(__name__)

GITHUB_REPO = "developer-hla/elca-bulletin-maker"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


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

    Returns a dict with ``current``, ``latest``, and ``download_url`` keys
    when an update is available, or ``None`` if up-to-date (or on any error).
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
        }
    except Exception:
        logger.debug("Update check failed", exc_info=True)
        return None
