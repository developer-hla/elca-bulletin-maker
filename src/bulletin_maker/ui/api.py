"""Python-JS bridge for the bulletin maker UI.

All public methods are exposed to JavaScript via pywebview's js_api.
Every method returns a dict with at least {"success": bool}.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import platform
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import webview
from PIL import Image

from bulletin_maker.exceptions import AuthError, BulletinError, NetworkError, UpdateError
from bulletin_maker.renderer import (
    generate_bulletin,
    generate_large_print,
    generate_leader_guide,
    generate_pulpit_prayers,
    generate_pulpit_scripture,
)
from bulletin_maker.renderer.season import (
    PrefaceType,
    detect_season,
    fill_seasonal_defaults,
    get_preface_options,
    get_seasonal_config,
)
from bulletin_maker.renderer.static_text import (
    AARONIC_BLESSING,
    CONFESSION_AND_FORGIVENESS,
    DISMISSAL_ENTRIES,
)
from bulletin_maker.renderer.text_utils import (
    DialogRole,
    clean_sns_html,
    group_psalm_verses,
    parse_dialog_html,
    preprocess_html,
)
from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.models import DayContent, HymnLyrics, ServiceConfig
from bulletin_maker.updater import check_for_update, install_update, is_install_writable

logger = logging.getLogger(__name__)


def _format_verse_label(selected: list[int]) -> str:
    """Build a compact verse label like 'Verses 1, 3-5' from sorted indices."""
    if not selected:
        return ""
    nums = sorted(selected)
    ranges: list[str] = []
    start = end = nums[0]
    for n in nums[1:]:
        if n == end + 1:
            end = n
        else:
            ranges.append(str(start) if start == end else f"{start}-{end}")
            start = end = n
    ranges.append(str(start) if start == end else f"{start}-{end}")
    label = ", ".join(ranges)
    return f"Verse {label}" if len(nums) == 1 else f"Verses {label}"


def _filter_verses(
    all_verses: list[str],
    selected: list[int] | None,
) -> tuple[list[str], str]:
    """Filter verses by 1-based indices and build a verse label.

    Returns (filtered_verses, verse_label).  If *selected* is None or
    includes all verses, returns the original list with an empty label.
    """
    total = len(all_verses)
    if not selected or len(selected) >= total:
        return all_verses, ""
    valid = sorted(i for i in selected if 1 <= i <= total)
    if not valid or len(valid) >= total:
        return all_verses, ""
    filtered = [all_verses[i - 1] for i in valid]
    return filtered, _format_verse_label(valid)


class BulletinAPI:
    """Bridge between the pywebview JS frontend and the Python backend."""

    def __init__(self, *, debug: bool = False) -> None:
        self._client: Optional[SundaysClient] = None
        self._day: Optional[DayContent] = None
        self._date_str: Optional[str] = None  # "YYYY-MM-DD" from last fetch
        self._window: Optional[webview.Window] = None
        self._hymn_cache: dict[str, dict] = {}
        self._debug: bool = debug

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    @staticmethod
    def _classify_error(error: Exception) -> str:
        """Classify an exception for the UI error_type field."""
        if isinstance(error, AuthError):
            return "auth"
        if isinstance(error, NetworkError):
            return "network"
        if isinstance(error, (ValueError, TypeError)):
            return "validation"
        return "internal"

    def _push_progress(self, step: str, detail: str, pct: int) -> None:
        """Push progress update to the JS frontend."""
        if self._window:
            payload = json.dumps({"step": step, "detail": detail, "pct": pct})
            self._window.evaluate_js(f"updateProgress({payload})")

    def _build_date_suffix(self) -> str:
        """Build the date + day portion of a filename.

        Returns e.g. ``2026.03.01 - First Sunday in Lent Year A``.
        If the selected date is not a Sunday, the weekday is prepended.
        """
        if not self._date_str:
            raise ValueError("No date selected")
        dt = datetime.strptime(self._date_str, "%Y-%m-%d")
        date_dot = dt.strftime("%Y.%m.%d")
        day_label = self._day.title
        title_match = re.search(r'\d{4}\s+(.+)', day_label)
        if title_match:
            day_label = title_match.group(1).strip()
        year_match = re.search(r',?\s*Year\s+([ABC])$', day_label)
        year_letter = year_match.group(1) if year_match else ""
        day_label = re.sub(r',?\s*Year\s+[ABC]$', '', day_label).strip()

        # If the date isn't a Sunday, prepend the weekday to clarify
        if dt.weekday() != 6:  # 6 = Sunday in Python
            weekday = dt.strftime("%A")
            day_label = f"{weekday} - {day_label}"

        if year_letter:
            day_label += " Year " + year_letter
        return f"{date_dot} - {day_label}"

    def _build_filename(self, doc_label: str) -> str:
        """Build a full filename like ``Bulletin - 2026.03.01 - First Sunday in Lent Year A.pdf``."""
        return f"{doc_label} - {self._build_date_suffix()}.pdf"

    def get_file_prefix(self) -> dict:
        """Return the date-suffix portion of filenames (for UI preview)."""
        try:
            if self._day is None or self._date_str is None:
                return {"success": False, "error": "No content fetched yet.",
                        "error_type": "validation"}
            return {"success": True, "prefix": self._build_date_suffix()}
        except (ValueError, BulletinError) as e:
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    def _get_client(self) -> SundaysClient:
        """Get or create the S&S client."""
        if self._client is None:
            self._client = SundaysClient()
        return self._client

    # ── Update Check ─────────────────────────────────────────────────

    def check_for_update(self) -> dict:
        """Check GitHub for a newer release."""
        result = check_for_update()
        if result:
            return {"success": True, "update_available": True, **result}
        return {"success": True, "update_available": False}

    def install_update(self, download_url: str) -> dict:
        """Download, install, and relaunch the updated application."""
        if not is_install_writable():
            return {
                "success": False,
                "error": "Install location is not writable.",
                "fallback_url": download_url,
            }

        try:
            install_update(download_url, progress_callback=self._push_progress)
            # If we get here on Windows, the bat script hasn't launched yet
            return {"success": True}
        except UpdateError as e:
            logger.exception("Update install failed")
            return {
                "success": False,
                "error": str(e),
                "fallback_url": download_url,
            }

    # ── Credential Storage ────────────────────────────────────────────

    @staticmethod
    def _config_path() -> Path:
        return Path.home() / ".bulletin-maker" / "config.json"

    def _read_config(self) -> dict:
        """Read config.json, returning empty dict on error."""
        try:
            path = self._config_path()
            if path.exists():
                return json.loads(path.read_text())
        except Exception:
            logger.debug("Could not read config", exc_info=True)
        return {}

    def _write_config(self, data: dict) -> None:
        """Write config.json with 0600 permissions."""
        try:
            path = self._config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2))
            path.chmod(0o600)
        except Exception:
            logger.debug("Could not write config", exc_info=True)

    def save_output_dir(self, path: str) -> dict:
        """Persist output directory preference."""
        data = self._read_config()
        data["output_dir"] = path
        self._write_config(data)
        return {"success": True}

    def get_saved_output_dir(self) -> dict:
        """Return saved output directory if set."""
        data = self._read_config()
        output_dir = data.get("output_dir", "")
        if output_dir and Path(output_dir).is_dir():
            return {"success": True, "path": output_dir}
        return {"success": False}

    # ── Past Runs ─────────────────────────────────────────────────────

    MAX_PAST_RUNS = 20

    @staticmethod
    def _past_runs_path() -> Path:
        return Path.home() / ".bulletin-maker" / "past_runs.json"

    def _read_past_runs(self) -> list:
        try:
            path = self._past_runs_path()
            if path.exists():
                data = json.loads(path.read_text())
                if isinstance(data, list):
                    return data
        except Exception:
            logger.debug("Could not read past runs", exc_info=True)
        return []

    def _write_past_runs(self, runs: list) -> None:
        try:
            path = self._past_runs_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(runs[: self.MAX_PAST_RUNS], indent=2))
        except Exception:
            logger.debug("Could not write past runs", exc_info=True)

    def save_past_run(self, form_data: dict, metadata: dict) -> dict:
        now = datetime.now()
        run = {
            "id": now.strftime("%Y%m%d%H%M%S"),
            "timestamp": now.isoformat(),
            "metadata": metadata,
            "form_data": form_data,
        }
        runs = self._read_past_runs()
        runs = [r for r in runs if r.get("form_data", {}).get("date") != form_data.get("date")]
        runs.insert(0, run)
        self._write_past_runs(runs)
        return {"success": True, "id": run["id"]}

    def get_past_runs(self) -> dict:
        runs = self._read_past_runs()
        summaries = [
            {
                "id": r.get("id", ""),
                "timestamp": r.get("timestamp", ""),
                "metadata": r.get("metadata", {}),
                "date": r.get("form_data", {}).get("date", ""),
            }
            for r in runs
        ]
        return {"success": True, "runs": summaries}

    def get_past_run(self, run_id: str) -> dict:
        for r in self._read_past_runs():
            if r.get("id") == run_id:
                return {"success": True, "form_data": r.get("form_data", {}), "metadata": r.get("metadata", {})}
        return {"success": False, "error": "Run not found.", "error_type": "validation"}

    def delete_past_run(self, run_id: str) -> dict:
        runs = self._read_past_runs()
        filtered = [r for r in runs if r.get("id") != run_id]
        if len(filtered) == len(runs):
            return {"success": False, "error": "Run not found.", "error_type": "validation"}
        self._write_past_runs(filtered)
        return {"success": True}

    # ── Credentials ───────────────────────────────────────────────────

    def login(self, username: str, password: str) -> dict:
        """Login to S&S with provided credentials."""
        try:
            client = self._get_client()
            client.login(username, password)
            return {"success": True, "username": username}
        except AuthError as e:
            return {"success": False, "error": str(e), "error_type": "auth"}
        except BulletinError as e:
            logger.exception("Login error")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    def logout(self) -> dict:
        """Close client session and reset state."""
        if self._client:
            self._client.close()
            self._client = None
        self._day = None
        self._date_str = None
        self._hymn_cache.clear()
        return {"success": True}

    # ── Preface Options ─────────────────────────────────────────────

    def get_preface_options(self) -> dict:
        """Return available preface options for the UI dropdown."""
        try:
            options = get_preface_options()
            return {"success": True, "prefaces": options}
        except BulletinError as e:
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    # ── Content Fetching ──────────────────────────────────────────────

    def fetch_day_content(self, date_str: str, date_display: str) -> dict:
        """Fetch S&S content for a date. Detect season and return defaults.

        Args:
            date_str: Date in "YYYY-MM-DD" format (from HTML date input).
            date_display: Human-readable date like "February 22, 2026".

        Returns dict with day title, season, reading citations, and
        seasonal default values for the liturgical settings.
        """
        try:
            # Convert "2026-02-22" to "2026-2-22" (S&S API format)
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return {"success": False, "error": f"Invalid date format: {date_str}",
                    "error_type": "validation"}

        try:
            client = self._get_client()
            api_date = f"{dt.year}-{dt.month}-{dt.day}"

            self._day = client.get_day_texts(api_date)
            self._date_str = date_str

            season = detect_season(self._day.title)
            seasonal = get_seasonal_config(season)

            # Extract day name from title
            day_name = self._day.title
            date_match = re.search(r'\d{4}\s+(.+)', day_name)
            if date_match:
                day_name = date_match.group(1).strip()
            day_name = re.sub(r',?\s*Year\s+[ABC]$', '', day_name).strip()

            readings = []
            for r in self._day.readings:
                readings.append({
                    "label": r.label,
                    "citation": r.citation,
                })

            return {
                "success": True,
                "title": self._day.title,
                "day_name": day_name,
                "season": season.value,
                "readings": readings,
                "defaults": {
                    "creed_type": seasonal.creed_default,
                    "include_kyrie": seasonal.has_kyrie,
                    "canticle": seasonal.canticle,
                    "eucharistic_form": seasonal.eucharistic_form,
                    "include_memorial_acclamation": seasonal.has_memorial_acclamation,
                    "preface": seasonal.preface.value,
                    "show_confession": seasonal.show_confession,
                    "show_nunc_dimittis": seasonal.show_nunc_dimittis,
                },
            }
        except AuthError as e:
            return {"success": False, "error": str(e), "auth_error": True,
                    "error_type": "auth"}
        except BulletinError as e:
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    # ── Reading Preview ─────────────────────────────────────────────────

    @staticmethod
    def _build_psalm_preview(text_html: str) -> str:
        """Build preview HTML for a psalm reading."""
        groups = group_psalm_verses(text_html)
        lines = []
        for g in groups:
            prefix = f'<sup>{g.verse_num}</sup>' if g.verse_num else ''
            cls = ' class="psalm-bold"' if g.bold else ''
            lines.append(f'<p{cls}>{prefix}{g.text}</p>')
            for c in g.continuations:
                cls = "psalm-bold psalm-cont" if c.bold else "psalm-cont"
                lines.append(f'<p class="{cls}">{c.text}</p>')
        return "\n".join(lines)

    def get_reading_preview(self, slot: str) -> dict:
        """Return rendered HTML for a reading preview."""
        if self._day is None:
            return {"success": False, "error": "No content fetched yet.",
                    "error_type": "validation"}

        slot_labels = {
            "first": "First Reading",
            "second": "Second Reading",
            "psalm": "Psalm",
            "gospel": "Gospel",
        }
        target_label = slot_labels.get(slot)
        if not target_label:
            return {"success": False, "error": f"Unknown slot: {slot}",
                    "error_type": "validation"}

        reading = None
        for r in self._day.readings:
            if r.label == target_label:
                reading = r
                break
        if not reading:
            return {"success": False,
                    "error": f"No {target_label} found for this date.",
                    "error_type": "validation"}

        try:
            if slot == "psalm":
                preview_html = self._build_psalm_preview(reading.text_html)
            else:
                body = reading.text_html
                body = re.sub(r'^<div[^>]*>', '', body)
                body = re.sub(r'</div>\s*$', '', body)
                preview_html = preprocess_html(body)

            return {
                "success": True,
                "label": reading.label,
                "citation": reading.citation,
                "intro": clean_sns_html(reading.intro),
                "preview_html": preview_html,
            }
        except BulletinError as e:
            logger.exception("Error getting reading preview")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    # ── Custom Reading ─────────────────────────────────────────────────

    def fetch_custom_reading(self, citation: str) -> dict:
        """Fetch a Bible passage from S&S for a custom reading citation."""
        try:
            client = self._get_client()
            html = client.search_passage(citation)
            return {"success": True, "text_html": html, "citation": citation}
        except BulletinError as e:
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    # ── Liturgical Texts ────────────────────────────────────────────────

    def get_liturgical_texts(self) -> dict:
        """Return named options for the 5 variable liturgical texts.

        Must be called after fetch_day_content() populates self._day.
        Each text has an ``options`` list of named presets (Ascension
        customs, S&S weekly variants, etc.) and a ``default`` key.
        The UI renders radio buttons from the options list.
        """
        try:
            if self._day is None:
                return {"success": False, "error": "No content fetched yet.",
                        "error_type": "validation"}

            day = self._day

            def _entries_to_dicts(entries):
                return [{"role": r.value, "text": t} for r, t in entries]

            # Parse S&S structured versions
            sns_confession = _entries_to_dicts(
                parse_dialog_html(day.confession_html)
            ) if day.confession_html else []

            sns_dismissal = _entries_to_dicts(
                parse_dialog_html(day.dismissal_html)
            ) if day.dismissal_html else []

            texts = {
                "prayer_of_day": {
                    "label": "Prayer of the Day",
                    "type": "text",
                    "default": "sns",
                    "options": [
                        {"key": "sns", "label": "This Week\u2019s (S&S)",
                         "data": clean_sns_html(day.prayer_of_the_day_html),
                         "disabled": not bool(day.prayer_of_the_day_html)},
                    ],
                },
                "confession": {
                    "label": "Confession and Forgiveness",
                    "type": "structured",
                    "default": "form_a",
                    "options": [
                        {"key": "form_a", "label": "ELW Form A",
                         "data": _entries_to_dicts(CONFESSION_AND_FORGIVENESS)},
                        {"key": "sns", "label": "This Week\u2019s (S&S)",
                         "data": sns_confession,
                         "disabled": not bool(sns_confession)},
                    ],
                },
                "offering_prayer": {
                    "label": "Offering Prayer",
                    "type": "text",
                    "default": "sns",
                    "options": [
                        {"key": "sns", "label": "This Week\u2019s (S&S)",
                         "data": clean_sns_html(day.offering_prayer_html),
                         "disabled": not bool(day.offering_prayer_html)},
                    ],
                },
                "prayer_after_communion": {
                    "label": "Prayer After Communion",
                    "type": "text",
                    "default": "sns",
                    "options": [
                        {"key": "sns", "label": "This Week\u2019s (S&S)",
                         "data": clean_sns_html(day.prayer_after_communion_html),
                         "disabled": not bool(day.prayer_after_communion_html)},
                    ],
                },
                "blessing": {
                    "label": "Blessing",
                    "type": "text",
                    "default": "aaronic",
                    "options": [
                        {"key": "aaronic", "label": "Aaronic Blessing",
                         "data": AARONIC_BLESSING},
                        {"key": "sns", "label": "This Week\u2019s (S&S)",
                         "data": clean_sns_html(day.blessing_html),
                         "disabled": not bool(day.blessing_html)},
                    ],
                },
                "dismissal": {
                    "label": "Dismissal",
                    "type": "structured",
                    "default": "standard",
                    "options": [
                        {"key": "standard",
                         "label": "Go in peace to love and serve the Lord",
                         "data": _entries_to_dicts(DISMISSAL_ENTRIES)},
                        {"key": "sns", "label": "This Week\u2019s (S&S)",
                         "data": sns_dismissal,
                         "disabled": not bool(sns_dismissal)},
                    ],
                },
            }

            return {"success": True, "texts": texts}
        except BulletinError as e:
            logger.exception("Error getting liturgical texts")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    # ── Hymns ─────────────────────────────────────────────────────────

    def search_hymn(self, number: str, collection: str = "ELW") -> dict:
        """Search S&S for a hymn by number.

        Returns title and verse count on success.
        """
        try:
            client = self._get_client()
            results = client.search_hymn(number, collection)

            if not results:
                return {"success": False,
                        "error": f"No results for {collection} {number}",
                        "error_type": "internal"}

            hymn = results[0]
            return {
                "success": True,
                "title": hymn.title,
                "atom_id": hymn.atom_id,
                "hymn_numbers": hymn.hymn_numbers,
                "has_words": bool(hymn.words_atom_id),
            }
        except BulletinError as e:
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    def fetch_hymn_lyrics(self, number: str, date_str: str,
                          collection: str = "ELW") -> dict:
        """Download and parse hymn lyrics from S&S.

        Args:
            number: Hymn number (e.g. "335").
            date_str: Date in "YYYY-MM-DD" format.
            collection: "ELW" or "ACS".
        """
        try:
            client = self._get_client()

            # Convert date for S&S use_date format (M/D/YYYY)
            # Fall back to today if no date provided (date is only for licensing)
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    dt = datetime.now()
            else:
                dt = datetime.now()
            use_date = f"{dt.month}/{dt.day}/{dt.year}"

            lyrics = client.fetch_hymn_lyrics(number, use_date, collection)

            cache_key = f"{collection}_{number}"
            self._hymn_cache[cache_key] = {
                "number": lyrics.number,
                "title": lyrics.title,
                "verses": lyrics.verses,
                "refrain": lyrics.refrain,
                "copyright": lyrics.copyright,
            }

            return {
                "success": True,
                "number": lyrics.number,
                "title": lyrics.title,
                "verse_count": len(lyrics.verses),
                "has_refrain": bool(lyrics.refrain),
            }
        except BulletinError as e:
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    # ── File Pickers ──────────────────────────────────────────────────

    def choose_output_directory(self) -> dict:
        """Open native folder picker dialog."""
        try:
            if not self._window:
                return {"success": False, "error": "Window not available",
                        "error_type": "internal"}

            result = self._window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory="",
            )
            if result and len(result) > 0:
                return {"success": True, "path": result[0]}
            return {"success": False, "error": "No folder selected",
                    "error_type": "validation"}
        except (OSError, RuntimeError) as e:
            logger.exception("Error choosing output directory")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    def get_cover_preview(self, path: str) -> dict:
        """Return a small base64 JPEG thumbnail for a cover image."""
        try:
            img = Image.open(path)
            img.thumbnail((150, 150))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            data = base64.b64encode(buf.getvalue()).decode()
            return {"success": True, "data_uri": f"data:image/jpeg;base64,{data}"}
        except (OSError, ValueError) as e:
            logger.debug("Cover preview failed: %s", e)
            return {"success": False, "error": str(e)}

    def choose_cover_image(self) -> dict:
        """Open native file picker for cover image."""
        try:
            if not self._window:
                return {"success": False, "error": "Window not available",
                        "error_type": "internal"}

            file_types = ("Image Files (*.jpg;*.jpeg;*.png;*.tif;*.tiff)",)
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                directory="",
                file_types=file_types,
            )
            if result and len(result) > 0:
                return {"success": True, "path": result[0]}
            return {"success": False, "error": "No file selected",
                    "error_type": "validation"}
        except (OSError, RuntimeError) as e:
            logger.exception("Error choosing cover image")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    # ── Generation helpers ─────────────────────────────────────────────

    def _build_hymn(self, form_data: dict, slot: str) -> Optional[HymnLyrics]:
        """Build a HymnLyrics from cached data for a form slot."""
        hymn_data = form_data.get(slot)
        if not hymn_data:
            return None
        number = hymn_data.get("number", "")
        collection = hymn_data.get("collection", "ELW")
        cache_key = f"{collection}_{number}"
        cached = self._hymn_cache.get(cache_key)
        if cached:
            all_verses = cached["verses"]
            selected = hymn_data.get("selected_verses")
            verses, verse_label = _filter_verses(all_verses, selected)
            return HymnLyrics(
                number=cached["number"],
                title=cached["title"],
                verses=verses,
                refrain=cached["refrain"],
                copyright=cached["copyright"],
                verse_label=verse_label,
            )
        # Minimal fallback — title only (no lyrics fetched)
        logger.warning("Hymn %s %s not in cache — large print will show title only",
                        collection, number)
        title = hymn_data.get("title", "")
        return HymnLyrics(
            number=f"{collection} {number}",
            title=title,
            verses=[],
        )

    @staticmethod
    def _parse_preface(value: str | None) -> PrefaceType | None:
        """Convert a preface string to PrefaceType, returning None on bad input."""
        if not value:
            return None
        try:
            return PrefaceType(value)
        except ValueError:
            logger.warning("Invalid preface value from UI: %r", value)
            return None

    @staticmethod
    def _parse_dialog_entries(raw: list | None) -> list | None:
        """Convert JSON dialog dicts back to (DialogRole, text) tuples."""
        if not raw:
            return None
        entries = []
        for e in raw:
            try:
                role = DialogRole(e.get("role", ""))
            except ValueError:
                role = DialogRole.NONE
            entries.append((role, e.get("text", "")))
        return entries

    def _build_service_config(self, form_data: dict) -> ServiceConfig:
        """Build a ServiceConfig from wizard form data."""
        return ServiceConfig(
            date=form_data.get("date", ""),
            date_display=form_data.get("date_display", ""),
            creed_type=form_data.get("creed_type"),
            include_kyrie=form_data.get("include_kyrie"),
            canticle=form_data.get("canticle"),
            eucharistic_form=form_data.get("eucharistic_form"),
            include_memorial_acclamation=form_data.get("include_memorial_acclamation"),
            preface=self._parse_preface(form_data.get("preface")),
            show_confession=form_data.get("show_confession"),
            show_nunc_dimittis=form_data.get("show_nunc_dimittis"),
            reading_overrides=form_data.get("reading_overrides") or None,
            include_baptism=form_data.get("include_baptism", False),
            baptism_candidate_names=form_data.get("baptism_candidate_names", ""),
            baptism_placement=form_data.get("baptism_placement", "after_welcome"),
            confession_entries=self._parse_dialog_entries(
                form_data.get("confession_entries")
            ),
            offering_prayer_text=form_data.get("offering_prayer_text") or None,
            prayer_after_communion_text=form_data.get("prayer_after_communion_text") or None,
            blessing_text=form_data.get("blessing_text") or None,
            dismissal_entries=self._parse_dialog_entries(
                form_data.get("dismissal_entries")
            ),
            gathering_hymn=self._build_hymn(form_data, "gathering_hymn"),
            sermon_hymn=self._build_hymn(form_data, "sermon_hymn"),
            communion_hymn=self._build_hymn(form_data, "communion_hymn"),
            sending_hymn=self._build_hymn(form_data, "sending_hymn"),
            prelude_title=form_data.get("prelude_title", ""),
            prelude_composer=form_data.get("prelude_composer", ""),
            prelude_performer=form_data.get("prelude_performer", ""),
            offertory_title=form_data.get("offertory_title", ""),
            offertory_composer=form_data.get("offertory_composer", ""),
            offertory_performer=form_data.get("offertory_performer", ""),
            postlude_title=form_data.get("postlude_title", ""),
            postlude_composer=form_data.get("postlude_composer", ""),
            postlude_performer=form_data.get("postlude_performer", ""),
            choral_title=form_data.get("choral_title", ""),
            cover_image=form_data.get("cover_image", ""),
        )

    # ── Generation ────────────────────────────────────────────────────

    def _generate_one(
        self, key: str, label: str, gen_fn: Callable, results: dict,
        errors: dict, step: int, total: int,
    ) -> None:
        """Run a single document generation with progress + error handling.

        Catches all exceptions to isolate individual document failures —
        one failing document must not prevent the others from generating.
        """
        pct = int(step / total * 95) if total else 0
        self._push_progress(key, f"[{step}/{total}] Generating {label}...", pct)
        try:
            path = gen_fn()
            results[key] = str(path)
            self._push_progress(key, f"[{step}/{total}] {label} saved", pct)
        except Exception as e:
            logger.exception("%s generation failed", label)
            errors[key] = str(e)
            self._push_progress(key, f"[{step}/{total}] {label} failed: {e}", pct)

    def generate_all(self, form_data: dict) -> dict:
        """Generate all 5 documents from the wizard form data."""
        try:
            if self._day is None:
                return {"success": False, "error": "No content fetched. Pick a date first.",
                        "error_type": "validation"}

            date = form_data.get("date")
            date_display = form_data.get("date_display")
            if not date or not date_display:
                return {"success": False,
                        "error": "Missing required fields: date and date_display.",
                        "error_type": "validation"}

            output_dir = Path(form_data.get("output_dir", "output"))
            output_dir.mkdir(parents=True, exist_ok=True)

            config = self._build_service_config(form_data)
            season = detect_season(self._day.title)
            fill_seasonal_defaults(config, season)

            selected = set(form_data.get("selected_docs") or [
                "bulletin", "prayers", "scripture", "large_print", "leader_guide",
            ])

            results: dict = {}
            errors: dict = {}
            creed_page = None
            total = len(selected)
            step = 0

            # 1. Bulletin (must be first — determines creed page)
            if "bulletin" in selected:
                step += 1
                pct = int(step / total * 95) if total else 0

                def _bulletin_progress(detail: str) -> None:
                    self._push_progress("bulletin", f"[{step}/{total}] Bulletin: {detail}", pct)

                def _gen_bulletin() -> Path:
                    nonlocal creed_page
                    path, creed_page = generate_bulletin(
                        self._day, config,
                        output_path=output_dir / self._build_filename("Bulletin for Congregation"),
                        season=season,
                        client=self._client,
                        keep_intermediates=self._debug,
                        on_progress=_bulletin_progress,
                    )
                    return path

                self._generate_one("bulletin", "Bulletin booklet", _gen_bulletin,
                                   results, errors, step, total)

            # 2. Pulpit Prayers (needs creed page from bulletin)
            if "prayers" in selected:
                step += 1
                creed_type = config.creed_type or "apostles"
                prayers_label = "NICENE" if creed_type == "nicene" else "APOSTLES"
                self._generate_one(
                    "prayers", "Pulpit prayers",
                    lambda: generate_pulpit_prayers(
                        self._day, config.date_display,
                        creed_type=creed_type, creed_page_num=creed_page,
                        output_path=output_dir / self._build_filename(f"Pulpit PRAYERS + {prayers_label}"),
                        keep_intermediates=self._debug,
                    ),
                    results, errors, step, total,
                )

            # 3. Pulpit Scripture
            if "scripture" in selected:
                step += 1
                self._generate_one(
                    "scripture", "Pulpit scripture",
                    lambda: generate_pulpit_scripture(
                        self._day, config.date_display,
                        output_path=output_dir / self._build_filename("Pulpit SCRIPTURE"),
                        config=config, keep_intermediates=self._debug,
                    ),
                    results, errors, step, total,
                )

            # 4. Large Print
            if "large_print" in selected:
                step += 1
                self._generate_one(
                    "large_print", "Large print",
                    lambda: generate_large_print(
                        self._day, config,
                        output_path=output_dir / self._build_filename("Full with Hymns LARGE PRINT"),
                        season=season, client=self._client,
                        keep_intermediates=self._debug,
                    ),
                    results, errors, step, total,
                )

            # 5. Leader Guide
            if "leader_guide" in selected:
                step += 1
                self._generate_one(
                    "leader_guide", "Leader guide",
                    lambda: generate_leader_guide(
                        self._day, config,
                        output_path=output_dir / self._build_filename("Leader Guide"),
                        season=season, client=self._client,
                        keep_intermediates=self._debug,
                    ),
                    results, errors, step, total,
                )

            self._push_progress("done", "Generation complete!", 100)

            return {
                "success": len(errors) == 0,
                "results": results,
                "errors": errors,
                "output_dir": str(output_dir),
            }
        except AuthError as e:
            logger.exception("Auth error during generation")
            return {"success": False, "error": str(e), "auth_error": True,
                    "error_type": "auth"}
        except BulletinError as e:
            logger.exception("Generation error")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    def check_existing_files(self, output_dir: str, selected_docs: list) -> dict:
        """Check if any target PDFs already exist in the output directory."""
        try:
            folder = Path(output_dir or "output")
            if not folder.exists() or self._day is None:
                return {"success": True, "existing": []}

            # Map doc keys to document labels
            doc_labels = {
                "bulletin": "Bulletin for Congregation",
                "scripture": "Pulpit SCRIPTURE",
                "large_print": "Full with Hymns LARGE PRINT",
                "leader_guide": "Leader Guide",
            }

            existing = []
            for doc in (selected_docs or []):
                if doc == "prayers":
                    # Prayers filename varies by creed type
                    suffix = self._build_date_suffix()
                    for f in folder.glob("Pulpit PRAYERS*"):
                        if f.is_file() and suffix in f.name:
                            existing.append(f.name)
                            break
                else:
                    label = doc_labels.get(doc, "")
                    if label:
                        target = folder / self._build_filename(label)
                        if target.exists():
                            existing.append(target.name)

            return {"success": True, "existing": existing}
        except (OSError, ValueError) as e:
            logger.exception("Error checking existing files")
            return {"success": True, "existing": []}

    # ── Utilities ─────────────────────────────────────────────────────

    def open_output_folder(self, path: str) -> dict:
        """Open a folder in the system file manager."""
        try:
            folder = Path(path)
            if not folder.exists():
                return {"success": False, "error": f"Folder not found: {path}",
                        "error_type": "validation"}

            system = platform.system()
            if system == "Darwin":
                subprocess.Popen(["open", str(folder)])
            elif system == "Windows":
                subprocess.Popen(["explorer", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])

            return {"success": True}
        except OSError as e:
            logger.exception("Error opening folder")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    def cleanup(self) -> None:
        """Close the S&S client session."""
        if self._client:
            self._client.close()
            self._client = None
