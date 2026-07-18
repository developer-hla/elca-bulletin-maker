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
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import webview
from PIL import Image

from bulletin_maker.core.content_views import (
    build_liturgical_text_options,
    build_reading_preview,
)
from bulletin_maker.core.documents import (
    DEFAULT_SELECTION,
    document_label,
    generate_documents,
)
from bulletin_maker.core.models import ServiceConfig
from bulletin_maker.core.naming import build_date_suffix, build_filename, extract_day_name
from bulletin_maker.core import past_runs
from bulletin_maker.core.profile import load_profile
from bulletin_maker.core.service_form import build_service_config
from bulletin_maker.exceptions import AuthError, BulletinError, NetworkError, UpdateError
from bulletin_maker.renderer.season import (
    PrefaceType,
    detect_season,
    fill_seasonal_defaults,
    get_preface_options,
    get_seasonal_config,
)
from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.models import DayContent
from bulletin_maker.updater import check_for_update, install_update, is_install_writable

logger = logging.getLogger(__name__)


def _help_html_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "bulletin_maker" / "ui" / "templates" / "help.html"
    return Path(__file__).resolve().parent / "templates" / "help.html"


class BulletinAPI:
    """Bridge between the pywebview JS frontend and the Python backend."""

    def __init__(self, *, debug: bool = False) -> None:
        self._client: Optional[SundaysClient] = None
        self._day: Optional[DayContent] = None
        self._date_str: Optional[str] = None  # "YYYY-MM-DD" from last fetch
        self._window: Optional[webview.Window] = None
        self._help_window: Optional[webview.Window] = None
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

    def get_file_prefix(self) -> dict:
        """Return the date-suffix portion of filenames (for UI preview)."""
        try:
            if self._day is None or self._date_str is None:
                return {"success": False, "error": "No content fetched yet.",
                        "error_type": "validation"}
            prefix = build_date_suffix(self._date_str, self._day.title)
            return {"success": True, "prefix": prefix}
        except (ValueError, BulletinError) as e:
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

    def _get_client(self) -> SundaysClient:
        """Get or create the S&S client."""
        if self._client is None:
            self._client = SundaysClient()
        return self._client

    # ── Congregation Profile ──────────────────────────────────────────

    def get_profile(self) -> dict:
        """Return congregation identity fields for UI display."""
        try:
            profile = load_profile()
            return {
                "success": True,
                "church_name": profile.church_name,
                "service_time": profile.service_time,
                "source_path": profile.source_path,
            }
        except BulletinError as e:
            return {"success": False, "error": str(e),
                    "error_type": self._classify_error(e)}

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

    def save_past_run(self, form_data: dict, metadata: dict) -> dict:
        run_id = past_runs.save_past_run(form_data, metadata)
        return {"success": True, "id": run_id}

    def get_past_runs(self) -> dict:
        return {"success": True, "runs": past_runs.list_past_runs()}

    def get_past_run(self, run_id: str) -> dict:
        run = past_runs.get_past_run(run_id)
        if run is None:
            return {"success": False, "error": "Run not found.",
                    "error_type": "validation"}
        return {"success": True, "form_data": run.get("form_data", {}),
                "metadata": run.get("metadata", {})}

    def delete_past_run(self, run_id: str) -> dict:
        if not past_runs.delete_past_run(run_id):
            return {"success": False, "error": "Run not found.",
                    "error_type": "validation"}
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

            day_name = extract_day_name(self._day.title)

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
                "warnings": self._day.content_warnings(),
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
        """Return rendered HTML for a reading preview."""
        if self._day is None:
            return {"success": False, "error": "No content fetched yet.",
                    "error_type": "validation"}
        try:
            preview = build_reading_preview(self._day, slot)
            return {"success": True, **preview}
        except (ValueError, BulletinError) as e:
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
        """Return named options for the 5 variable liturgical texts."""
        try:
            if self._day is None:
                return {"success": False, "error": "No content fetched yet.",
                        "error_type": "validation"}
            return {"success": True,
                    "texts": build_liturgical_text_options(self._day)}
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

    def _build_service_config(self, form_data: dict) -> ServiceConfig:
        """Build a ServiceConfig from wizard form data + hymn cache."""
        return build_service_config(form_data, self._hymn_cache)

    # ── Generation ────────────────────────────────────────────────────

    def generate_all(self, form_data: dict) -> dict:
        """Generate the selected documents from the wizard form data.

        Thin adapter over core.documents.generate_documents — validates
        form data, builds the ServiceConfig, and adapts progress pushes.
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
            config = self._build_service_config(form_data)
            season = detect_season(self._day.title)
            fill_seasonal_defaults(config, season)

            selected = set(form_data.get("selected_docs") or DEFAULT_SELECTION)

            outcome = generate_documents(
                self._day, config, output_dir,
                season=season,
                client=self._client,
                selected=selected,
                keep_intermediates=self._debug,
                on_progress=self._push_progress,
            )

            return {
                "success": outcome.success,
                "results": outcome.results,
                "errors": outcome.errors,
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

            existing = []
            for doc in (selected_docs or []):
                if doc == "prayers":
                    # Prayers filename varies by creed type
                    suffix = build_date_suffix(self._date_str, self._day.title)
                    for f in folder.glob("Pulpit PRAYERS*"):
                        if f.is_file() and suffix in f.name:
                            existing.append(f.name)
                            break
                else:
                    label = document_label(doc)
                    target = folder / build_filename(
                        label, self._date_str, self._day.title)
                    if target.exists():
                        existing.append(target.name)

            return {"success": True, "existing": existing}
        except (KeyError, OSError, ValueError):
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

    def open_help_window(self) -> dict:
        """Open the user help guide in a separate window."""
        if self._help_window is not None:
            return {"success": True, "already_open": True}

        help_path = _help_html_path()
        if not help_path.exists():
            logger.error("Help file not found at %s", help_path)
            return {"success": False, "error": "Help file not found."}

        window = webview.create_window(
            title="Bulletin Maker — Help",
            url=str(help_path),
            width=720,
            height=820,
            min_size=(500, 600),
            text_select=True,
        )
        window.events.closed += self._on_help_closed
        self._help_window = window
        return {"success": True}

    def _on_help_closed(self, *_args) -> None:
        self._help_window = None

    def cleanup(self) -> None:
        """Close the S&S client session and any open child windows."""
        if self._help_window:
            try:
                self._help_window.destroy()
            except Exception:
                logger.warning("Help window already destroyed at cleanup")
            self._help_window = None
        if self._client:
            self._client.close()
            self._client = None
