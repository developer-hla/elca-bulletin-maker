"""Notation image management — static assets and dynamic hymn fetching.

Handles two kinds of notation images:
  1. Liturgical setting images (Kyrie, Sanctus, etc.) — resolved per
     LiturgicalSetting. Setting Two ships bundled in assets/; other
     settings download on demand (via the user's S&S login) into
     ~/.bulletin-maker/assets/{setting}/.
  2. Dynamic hymn images (communion hymn) — fetched from S&S per Sunday,
     cached to output/images/.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bulletin_maker.sns.client import SundaysClient

from bulletin_maker.exceptions import ContentNotFoundError
from bulletin_maker.renderer.season import LiturgicalSeason, PrefaceType
from bulletin_maker.renderer.settings import (
    DEFAULT_SETTING_KEY,
    USER_ASSETS_DIR,
    LiturgicalSetting,
    get_setting,
)
from bulletin_maker.sns.models import (
    CANTICLE_GLORY_TO_GOD,
    CANTICLE_THIS_IS_THE_FEAST,
)

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
GOSPEL_ACCLAMATION_DIR = ASSETS_DIR / "gospel_acclamation"

# ── S&S Library atom-code suffixes ───────────────────────────────────

# Canonical piece name → atom-code piece segment. Full code is
# f"{setting.atom_prefix}_{segment}_m" (melody/assembly edition).
_PIECE_ATOM_SEGMENTS = {
    "kyrie":                     "kyrie",
    CANTICLE_GLORY_TO_GOD:       "glory",
    CANTICLE_THIS_IS_THE_FEAST:  "feast",
    "great_thanksgiving":        "dialogue",
    "sanctus":                   "holy",
    "agnus_dei":                 "lamb",
    "nunc_dimittis":             "nowlord",
    "memorial_acclamation":      "christ",
    "amen":                      "amen",
}

def _ga_atom_segment(setting: LiturgicalSetting, variant: str) -> str:
    """Atom segment for a Gospel Acclamation variant.

    The Lenten verse is "lentaccl" in every setting; the standard
    acclamation segment varies per setting ("accltext" vs "alleluia").
    """
    if variant == "lenten_verse":
        return "lentaccl"
    return setting.ga_segment

# Season → Gospel Acclamation variant name
_GA_SEASON_MAP = {
    LiturgicalSeason.ADVENT: "alleluia",
    LiturgicalSeason.CHRISTMAS: "alleluia",
    LiturgicalSeason.EPIPHANY: "alleluia",
    LiturgicalSeason.LENT: "lenten_verse",
    LiturgicalSeason.EASTER: "alleluia",
    LiturgicalSeason.PENTECOST: "alleluia",
    LiturgicalSeason.CHRISTMAS_EVE: "alleluia",
}

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff")


# ── Internal helpers ─────────────────────────────────────────────────

def _resolve_setting(setting: LiturgicalSetting | None) -> LiturgicalSetting:
    return setting if setting is not None else get_setting(DEFAULT_SETTING_KEY)


def _setting_dir(setting: LiturgicalSetting) -> Path:
    """Notation directory for a setting — bundled assets or user cache."""
    if setting.bundled:
        return ASSETS_DIR / setting.key
    return USER_ASSETS_DIR / setting.key


def _ga_dir(setting: LiturgicalSetting) -> Path:
    if setting.bundled:
        return GOSPEL_ACCLAMATION_DIR
    return USER_ASSETS_DIR / setting.key / "gospel_acclamation"


def _find_image(directory: Path, stem: str) -> Path | None:
    """Find an image file with the given stem in directory, any extension."""
    for ext in _IMAGE_EXTENSIONS:
        path = directory / f"{stem}{ext}"
        if path.exists():
            return path
    return None


def _detect_extension(image_bytes: bytes) -> str:
    """Detect image format from magic bytes."""
    if image_bytes[:4] == b"\x89PNG":
        return ".png"
    if image_bytes[:2] in (b"II", b"MM"):
        return ".tif"
    return ".jpg"  # S&S default


def _download_library_image(client: SundaysClient, atom_code: str,
                            dest_dir: Path, stem: str) -> Path:
    """Download a single image from S&S Library by atom code."""
    from bulletin_maker.sns.client import BASE

    url = f"{BASE}/File/GetImage?atomCode={atom_code}"
    image_bytes = client.download_image(url)

    ext = _detect_extension(image_bytes)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / f"{stem}{ext}"
    out_path.write_bytes(image_bytes)
    return out_path


def _resolve_image(
    directory: Path, stem: str, atom_code: str,
    client: SundaysClient | None, missing_hint: str,
) -> Path:
    """Find an image on disk, downloading it on miss when a client is given."""
    found = _find_image(directory, stem)
    if found is not None:
        return found
    if client is not None:
        logger.debug("Downloading %s (atom: %s)...", stem, atom_code)
        return _download_library_image(client, atom_code, directory, stem)
    raise FileNotFoundError(
        f"Notation image not found for '{stem}' in {directory}\n{missing_hint}"
    )


# ── Setting image lookup ─────────────────────────────────────────────

def get_setting_image(
    piece: str,
    *,
    setting: LiturgicalSetting | None = None,
    client: SundaysClient | None = None,
) -> Path:
    """Return the notation image path for a liturgical setting piece.

    Args:
        piece: One of the keys in _PIECE_ATOM_SEGMENTS (e.g., "kyrie",
               "sanctus", "agnus_dei").
        setting: The liturgical setting (defaults to Setting Two).
        client: Optional authenticated S&S client — enables on-demand
            download for settings whose assets aren't bundled.

    Raises:
        ValueError: If piece name is not recognized.
        FileNotFoundError: If the asset is missing and no client given.
    """
    if piece not in _PIECE_ATOM_SEGMENTS:
        raise ValueError(
            f"Unknown setting piece: {piece!r}. "
            f"Valid pieces: {', '.join(_PIECE_ATOM_SEGMENTS)}"
        )
    setting = _resolve_setting(setting)
    if piece in setting.missing_pieces:
        raise ContentNotFoundError(
            f"{setting.label} does not include a '{piece}' — "
            "the section will be omitted."
        )
    atom_code = f"{setting.atom_prefix}_{_PIECE_ATOM_SEGMENTS[piece]}_m"
    return _resolve_image(
        _setting_dir(setting), piece, atom_code, client,
        "Sign in to S&S so the notation can be downloaded, or see assets/README.md",
    )


def get_gospel_acclamation_image(
    season: LiturgicalSeason,
    *,
    setting: LiturgicalSetting | None = None,
    client: SundaysClient | None = None,
) -> Path:
    """Return the Gospel Acclamation image path for the given season."""
    setting = _resolve_setting(setting)
    variant = _GA_SEASON_MAP.get(season, "alleluia")
    atom_code = f"{setting.atom_prefix}_{_ga_atom_segment(setting, variant)}_m"
    return _resolve_image(
        _ga_dir(setting), variant, atom_code, client,
        "Sign in to S&S so the notation can be downloaded, or see assets/README.md",
    )


def get_offertory_image() -> Path:
    """Return the path to the bundled offertory hymn notation image."""
    found = _find_image(ASSETS_DIR, "offertory")
    if found is None:
        raise FileNotFoundError(
            f"Offertory image not found in {ASSETS_DIR}\n"
            f"Run scripts/download_offertory_asset.py to fetch it."
        )
    return found


def get_preface_image(
    preface: PrefaceType,
    *,
    setting: LiturgicalSetting | None = None,
    client: SundaysClient | None = None,
) -> Path:
    """Return the sung preface notation image path."""
    setting = _resolve_setting(setting)
    stem = f"preface_{preface.value}"
    atom_code = f"{setting.atom_prefix}_pref_{preface.value}_m"
    return _resolve_image(
        _setting_dir(setting), stem, atom_code, client,
        "Sign in to S&S so the notation can be downloaded, or see assets/README.md",
    )


# ── Bulk download from S&S Library ───────────────────────────────────

def download_setting_assets(
    client: SundaysClient,
    setting: LiturgicalSetting | None = None,
) -> dict[str, Path]:
    """Download a setting's pieces + Gospel Acclamation images from S&S."""
    setting = _resolve_setting(setting)
    downloaded: dict[str, Path] = {}
    for piece in _PIECE_ATOM_SEGMENTS:
        if piece in setting.missing_pieces:
            continue
        downloaded[piece] = get_setting_image(
            piece, setting=setting, client=client)
    for variant in ("alleluia", "lenten_verse"):
        atom_code = f"{setting.atom_prefix}_{_ga_atom_segment(setting, variant)}_m"
        downloaded[f"ga_{variant}"] = _resolve_image(
            _ga_dir(setting), variant, atom_code, client, "")
    return downloaded


# ── Dynamic hymn image fetching ──────────────────────────────────────

# Default cache directory for downloaded hymn images (relative to CWD)
_DEFAULT_CACHE_DIR = Path("output") / "images"


def fetch_hymn_image(
    client: SundaysClient,
    number: str,
    collection: str = "ELW",
    *,
    cache_dir: Path | None = None,
    image_type: str = "melody",
) -> Path:
    """Search for a hymn and download its notation image.

    Uses the existing S&S client pipeline: search -> get_hymn_details ->
    download_image. Caches the result by hymn number so repeated calls
    don't re-download.

    Args:
        client: An authenticated SundaysClient.
        number: Hymn number (e.g., "504").
        collection: Hymn collection (default "ELW").
        cache_dir: Where to save downloaded images. Defaults to output/images/.
        image_type: "melody" or "harmony".

    Returns:
        Path to the downloaded image file.

    Raises:
        RuntimeError: If the hymn or image URL can't be found.
    """
    cache_dir = cache_dir or _DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Check cache first
    cache_key = f"{collection}{number}_{image_type}"
    found = _find_image(cache_dir, cache_key)
    if found:
        logger.debug("Using cached image: %s", found)
        return found

    # Search for the hymn
    results = client.search_hymn(number, collection=collection)
    if not results:
        raise ContentNotFoundError(f"No results for {collection} {number}")

    hymn = results[0]

    # Get details — prefer atom_code for full-resolution (300 DPI) images.
    # The pre-built image URLs contain width=700&height=700 params that
    # return 96 DPI web previews; using the atom code directly gives the
    # full library version.
    details = client.get_hymn_details(hymn.atom_id)

    suffix = "_m" if image_type == "melody" else "_h"
    if details.atom_code:
        url = f"/File/GetImage?atomCode={details.atom_code}{suffix}"
    elif image_type == "melody":
        url = details.melody_image_url
    else:
        url = details.harmony_image_url

    if not url:
        raise ContentNotFoundError(
            f"No {image_type} image URL for {collection} {number} "
            f"(atom_id={hymn.atom_id})"
        )

    # Download
    image_bytes = client.download_image(url)
    ext = _detect_extension(image_bytes)

    out_path = cache_dir / f"{cache_key}{ext}"
    out_path.write_bytes(image_bytes)
    logger.debug("Downloaded %s image: %s", image_type, out_path)

    return out_path
