"""Python-JS bridge for the bulletin maker UI.

All public methods are exposed to JavaScript via pywebview's js_api.
Every method returns a dict with at least {"success": bool}.
"""

from __future__ import annotations

import json
import logging
import platform
import subprocess
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import webview

from bulletin_maker.exceptions import AuthError, BulletinError, NetworkError
from bulletin_maker.renderer.text_utils import DialogRole, clean_sns_html, parse_dialog_html
from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.models import DayContent, HymnLyrics, ServiceConfig
from bulletin_maker.renderer.season import (
    PrefaceType,
    detect_season,
    fill_seasonal_defaults,
    get_seasonal_config,
)

logger = logging.getLogger(__name__)


class BulletinAPI:
    """Bridge between the pywebview JS frontend and the Python backend."""

    def __init__(self) -> None:
        self._client: Optional[SundaysClient] = None
        self._day: Optional[DayContent] = None
        self._date_str: Optional[str] = None  # "YYYY-MM-DD" from last fetch
        self._window: Optional[webview.Window] = None
        self._hymn_cache: dict[str, dict] = {}

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
        except Exception as e:
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
        from bulletin_maker.updater import check_for_update
        result = check_for_update()
        if result:
            return {"success": True, "update_available": True, **result}
        return {"success": True, "update_available": False}

    def install_update(self, download_url: str) -> dict:
        """Download, install, and relaunch the updated application."""
        from bulletin_maker.exceptions import UpdateError
        from bulletin_maker.updater import install_update, is_install_writable

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

    def _save_credentials(self, username: str, password: str) -> None:
        """Save credentials to ~/.bulletin-maker/config.json."""
        data = self._read_config()
        data["username"] = username
        data["password"] = password
        self._write_config(data)

    def _clear_credentials(self) -> None:
        """Remove saved credentials from config.json."""
        data = self._read_config()
        data.pop("username", None)
        data.pop("password", None)
        self._write_config(data)

    def get_saved_credentials(self) -> dict:
        """Return saved credentials if they exist."""
        data = self._read_config()
        username = data.get("username", "")
        password = data.get("password", "")
        if username and password:
            return {"success": True, "username": username, "password": password}
        return {"success": False}

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

    # ── Credentials ───────────────────────────────────────────────────

    def login(self, username: str, password: str) -> dict:
        """Login to S&S with provided credentials."""
        try:
            client = self._get_client()
            client.login(username, password)
            self._save_credentials(username, password)
            return {"success": True, "username": username}
        except AuthError as e:
            return {"success": False, "error": str(e), "error_type": "auth"}
        except Exception as e:
            logger.exception("Login error")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    def logout(self) -> dict:
        """Close client session and reset state."""
        try:
            if self._client:
                self._client.close()
                self._client = None
            self._day = None
            self._date_str = None
            self._hymn_cache.clear()
            self._clear_credentials()
            return {"success": True}
        except Exception as e:
            logger.exception("Logout error")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    # ── Preface Options ─────────────────────────────────────────────

    def get_preface_options(self) -> dict:
        """Return available preface options for the UI dropdown."""
        from bulletin_maker.renderer.season import get_preface_options
        try:
            options = get_preface_options()
            return {"success": True, "prefaces": options}
        except Exception as e:
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
            client = self._get_client()

            # Convert "2026-02-22" to "2026-2-22" (S&S API format)
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                return {"success": False, "error": f"Invalid date format: {date_str}",
                        "error_type": "validation"}
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

    def get_reading_preview(self, slot: str) -> dict:
        """Return rendered HTML for a reading preview.

        Args:
            slot: "first", "second", "psalm", or "gospel".
        """
        from bulletin_maker.renderer.text_utils import (
            clean_sns_html,
            group_psalm_verses,
            preprocess_html,
        )

        try:
            if self._day is None:
                return {"success": False, "error": "No content fetched yet.",
                        "error_type": "validation"}

            # Find the matching reading
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

            # Build preview HTML
            if slot == "psalm":
                groups = group_psalm_verses(reading.text_html)
                lines = []
                for g in groups:
                    prefix = f'<sup>{g.verse_num}</sup>' if g.verse_num else ''
                    if g.bold:
                        lines.append(f'<p class="psalm-bold">{prefix}{g.text}</p>')
                    else:
                        lines.append(f'<p>{prefix}{g.text}</p>')
                    for c in g.continuations:
                        if c.bold:
                            lines.append(
                                f'<p class="psalm-bold psalm-cont">{c.text}</p>')
                        else:
                            lines.append(
                                f'<p class="psalm-cont">{c.text}</p>')
                preview_html = "\n".join(lines)
            else:
                # Strip outer S&S wrapper divs, keep inner HTML
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
        except Exception as e:
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
        from bulletin_maker.renderer.static_text import (
            AARONIC_BLESSING,
            CONFESSION_AND_FORGIVENESS,
            DISMISSAL_ENTRIES,
        )

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
        except Exception as e:
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
        except Exception as e:
            logger.exception("Error choosing output directory")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    def get_cover_preview(self, path: str) -> dict:
        """Return a small base64 JPEG thumbnail for a cover image."""
        try:
            import base64
            import io
            from PIL import Image

            img = Image.open(path)
            img.thumbnail((150, 150))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            data = base64.b64encode(buf.getvalue()).decode()
            return {"success": True, "data_uri": f"data:image/jpeg;base64,{data}"}
        except Exception as e:
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
        except Exception as e:
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
            return HymnLyrics(
                number=cached["number"],
                title=cached["title"],
                verses=cached["verses"],
                refrain=cached["refrain"],
                copyright=cached["copyright"],
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
        return [(DialogRole(e.get("role", "")), e.get("text", ""))
                for e in raw]

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
            prelude_performer=form_data.get("prelude_performer", ""),
            postlude_title=form_data.get("postlude_title", ""),
            postlude_performer=form_data.get("postlude_performer", ""),
            choral_title=form_data.get("choral_title", ""),
            cover_image=form_data.get("cover_image", ""),
        )

    # ── Generation ────────────────────────────────────────────────────

    def generate_all(self, form_data: dict) -> dict:
        """Generate all 5 documents from the wizard form data.

        form_data keys:
            date, date_display, creed_type, include_kyrie, canticle,
            eucharistic_form, include_memorial_acclamation,
            gathering_hymn, sermon_hymn, communion_hymn, sending_hymn,
            prelude_title, prelude_performer, postlude_title,
            postlude_performer, choral_title, cover_image, output_dir
        """
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

            results = {}
            errors = {}
            creed_page = None  # Set by bulletin generation

            from bulletin_maker.renderer import (
                generate_bulletin,
                generate_large_print,
                generate_leader_guide,
                generate_pulpit_prayers,
                generate_pulpit_scripture,
            )

            total = len(selected)
            step = 0

            # 1. Bulletin (must be first — determines creed page)
            if "bulletin" in selected:
                step += 1
                self._push_progress("bulletin", f"[{step}/{total}] Generating bulletin booklet...", 10)
                try:
                    bulletin_path, creed_page = generate_bulletin(
                        self._day, config,
                        output_path=output_dir / self._build_filename("Bulletin for Congregation"),
                        season=season,
                        client=self._client,
                    )
                    results["bulletin"] = str(bulletin_path)
                    self._push_progress("bulletin", f"[{step}/{total}] Bulletin saved (creed p.{creed_page})", 30)
                except Exception as e:
                    logger.exception("Bulletin generation failed")
                    errors["bulletin"] = str(e)
                    self._push_progress("bulletin", f"[{step}/{total}] Bulletin failed: {e}", 30)

            # 2. Pulpit Prayers (needs creed page from bulletin)
            if "prayers" in selected:
                step += 1
                self._push_progress("prayers", f"[{step}/{total}] Generating pulpit prayers...", 40)
                try:
                    creed_type = config.creed_type or "apostles"
                    prayers_label = "NICENE" if creed_type == "nicene" else "APOSTLES"
                    prayers_path = generate_pulpit_prayers(
                        self._day,
                        config.date_display,
                        creed_type=creed_type,
                        creed_page_num=creed_page,
                        output_path=output_dir / self._build_filename(f"Pulpit PRAYERS + {prayers_label}"),
                    )
                    results["prayers"] = str(prayers_path)
                    self._push_progress("prayers", f"[{step}/{total}] Pulpit prayers saved", 55)
                except Exception as e:
                    logger.exception("Pulpit prayers generation failed")
                    errors["prayers"] = str(e)
                    self._push_progress("prayers", f"[{step}/{total}] Prayers failed: {e}", 55)

            # 3. Pulpit Scripture
            if "scripture" in selected:
                step += 1
                self._push_progress("scripture", f"[{step}/{total}] Generating pulpit scripture...", 60)
                try:
                    scripture_path = generate_pulpit_scripture(
                        self._day,
                        config.date_display,
                        output_path=output_dir / self._build_filename("Pulpit SCRIPTURE"),
                        config=config,
                    )
                    results["scripture"] = str(scripture_path)
                    self._push_progress("scripture", f"[{step}/{total}] Pulpit scripture saved", 75)
                except Exception as e:
                    logger.exception("Pulpit scripture generation failed")
                    errors["scripture"] = str(e)
                    self._push_progress("scripture", f"[{step}/{total}] Scripture failed: {e}", 75)

            # 4. Large Print
            if "large_print" in selected:
                step += 1
                self._push_progress("large_print", f"[{step}/{total}] Generating large print...", 75)
                try:
                    lp_path = generate_large_print(
                        self._day, config,
                        output_path=output_dir / self._build_filename("Full with Hymns LARGE PRINT"),
                        season=season,
                    )
                    results["large_print"] = str(lp_path)
                    self._push_progress("large_print", f"[{step}/{total}] Large print saved", 85)
                except Exception as e:
                    logger.exception("Large print generation failed")
                    errors["large_print"] = str(e)
                    self._push_progress("large_print", f"[{step}/{total}] Large print failed: {e}", 85)

            # 5. Leader Guide
            if "leader_guide" in selected:
                step += 1
                self._push_progress("leader_guide", f"[{step}/{total}] Generating leader guide...", 87)
                try:
                    lg_path = generate_leader_guide(
                        self._day, config,
                        output_path=output_dir / self._build_filename("Leader Guide"),
                        season=season,
                    )
                    results["leader_guide"] = str(lg_path)
                    self._push_progress("leader_guide", f"[{step}/{total}] Leader guide saved", 95)
                except Exception as e:
                    logger.exception("Leader guide generation failed")
                    errors["leader_guide"] = str(e)
                    self._push_progress("leader_guide", f"[{step}/{total}] Leader guide failed: {e}", 95)

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
        except Exception as e:
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
                    for f in folder.iterdir():
                        if f.is_file() and f.name.startswith("Pulpit PRAYERS"):
                            suffix = self._build_date_suffix()
                            if suffix in f.name:
                                existing.append(f.name)
                                break
                else:
                    label = doc_labels.get(doc, "")
                    if label:
                        target = folder / self._build_filename(label)
                        if target.exists():
                            existing.append(target.name)

            return {"success": True, "existing": existing}
        except Exception as e:
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
        except Exception as e:
            logger.exception("Error opening folder")
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    def cleanup(self) -> None:
        """Close the S&S client session."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
