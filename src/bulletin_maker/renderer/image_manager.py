"""Notation image management — static assets and dynamic hymn fetching.

Handles two kinds of notation images:
  1. Static liturgical setting images (Kyrie, Sanctus, etc.) — downloaded
     once from S&S Library via atom codes, stored in assets/
  2. Dynamic hymn images (communion hymn) — fetched from S&S per Sunday,
     cached to output/images/

The Large Print document only needs the Gospel Acclamation image.
The standard bulletin needs all setting pieces + communion hymn.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bulletin_maker.sns.client import SundaysClient

from bulletin_maker.exceptions import ContentNotFoundError
from bulletin_maker.renderer.season import LiturgicalSeason

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
SETTING_TWO_DIR = ASSETS_DIR / "setting_two"
GOSPEL_ACCLAMATION_DIR = ASSETS_DIR / "gospel_acclamation"

# ── S&S Library atom codes ───────────────────────────────────────────

# Maps our canonical piece names → S&S Library atom codes
# These are used with /File/GetImage?atomCode={code} to download images.
_SETTING_TWO_ATOM_CODES = {
    "kyrie":              "elw_hc2_kyrie_m",
    "glory_to_god":       "elw_hc2_glory_m",
    "this_is_the_feast":  "elw_hc2_feast_m",
    "great_thanksgiving": "elw_hc2_dialogue_m",
    "sanctus":            "elw_hc2_holy_m",
    "agnus_dei":          "elw_hc2_lamb_m",
    "nunc_dimittis":      "elw_hc2_nowlord_m",
    "memorial_acclamation": "elw_hc2_christ_m",
    "amen":               "elw_hc2_amen_m",
}

_GOSPEL_ACCLAMATION_ATOM_CODES = {
    "alleluia":      "elw_hc2_accltext_m",   # Standard (Ordinary, Epiphany, Easter)
    "lenten_verse":  "elw_hc2_lentaccl_m",   # Lent ("Return to the Lord")
    "advent":        "elw_hc2_accltext_m",    # Advent uses same alleluia melody
}

# Preface atom codes (seasonal) — for future bulletin use
_PREFACE_ATOM_CODES = {
    "sundays":     "elw_hc2_pref_sundays_m",
    "advent":      "elw_hc2_pref_advent_m",
    "christmas":   "elw_hc2_pref_christmas_m",
    "epiphany":    "elw_hc2_pref_epiphany_m",
    "lent":        "elw_hc2_pref_lent_m",
    "easter":      "elw_hc2_pref_easter_m",
    "pentecost":   "elw_hc2_pref_pentecost_m",
}

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


# ── Static setting image lookup ──────────────────────────────────────

def get_setting_image(piece: str) -> Path:
    """Return the path to a Setting Two notation image.

    Args:
        piece: One of the keys in _SETTING_TWO_ATOM_CODES (e.g., "kyrie",
               "sanctus", "agnus_dei").

    Returns:
        Path to the image file.

    Raises:
        ValueError: If piece name is not recognized.
        FileNotFoundError: If the asset file hasn't been downloaded yet.
    """
    if piece not in _SETTING_TWO_ATOM_CODES:
        raise ValueError(
            f"Unknown setting piece: {piece!r}. "
            f"Valid pieces: {', '.join(_SETTING_TWO_ATOM_CODES)}"
        )
    found = _find_image(SETTING_TWO_DIR, piece)
    if found is None:
        raise FileNotFoundError(
            f"Setting image not found for '{piece}' in {SETTING_TWO_DIR}\n"
            f"Run download_setting_assets() or see assets/README.md"
        )
    return found


def get_gospel_acclamation_image(season: LiturgicalSeason) -> Path:
    """Return the path to the Gospel Acclamation image for the given season.

    Args:
        season: The liturgical season.

    Returns:
        Path to the image file.

    Raises:
        FileNotFoundError: If the asset file hasn't been downloaded yet.
    """
    variant = _GA_SEASON_MAP.get(season, "alleluia")
    found = _find_image(GOSPEL_ACCLAMATION_DIR, variant)
    if found is None:
        raise FileNotFoundError(
            f"Gospel Acclamation image not found for '{variant}' in "
            f"{GOSPEL_ACCLAMATION_DIR}\n"
            f"Run download_setting_assets() or see assets/README.md"
        )
    return found


# ── Bulk download from S&S Library ───────────────────────────────────

def download_setting_assets(client: SundaysClient) -> dict[str, Path]:
    """Download all Setting Two + Gospel Acclamation images from S&S Library.

    Uses the authenticated client to fetch images via their atom codes.
    Skips files that already exist. Returns a dict of piece name → file path.
    """
    downloaded: dict[str, Path] = {}

    # Setting Two pieces
    for piece, atom_code in _SETTING_TWO_ATOM_CODES.items():
        existing = _find_image(SETTING_TWO_DIR, piece)
        if existing:
            logger.info("Already have: %s", existing.name)
            downloaded[piece] = existing
            continue

        logger.info("Downloading %s (atom: %s)...", piece, atom_code)
        path = _download_library_image(client, atom_code, SETTING_TWO_DIR, piece)
        downloaded[piece] = path
        logger.info("  Saved: %s", path.name)

    # Gospel Acclamation variants
    for variant, atom_code in _GOSPEL_ACCLAMATION_ATOM_CODES.items():
        existing = _find_image(GOSPEL_ACCLAMATION_DIR, variant)
        if existing:
            logger.info("Already have: %s", existing.name)
            downloaded[f"ga_{variant}"] = existing
            continue

        logger.info("Downloading GA %s (atom: %s)...", variant, atom_code)
        path = _download_library_image(
            client, atom_code, GOSPEL_ACCLAMATION_DIR, variant,
        )
        downloaded[f"ga_{variant}"] = path
        logger.info("  Saved: %s", path.name)

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
        logger.info("Using cached image: %s", found)
        return found

    # Search for the hymn
    results = client.search_hymn(number, collection=collection)
    if not results:
        raise ContentNotFoundError(f"No results for {collection} {number}")

    hymn = results[0]

    # Get details (image URLs)
    details = client.get_hymn_details(hymn.atom_id)
    if image_type == "melody":
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
    logger.info("Downloaded %s image: %s", image_type, out_path)

    return out_path
