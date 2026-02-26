"""Desktop application entry point — pywebview window + BulletinAPI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import webview

from bulletin_maker.ui.api import BulletinAPI

logger = logging.getLogger(__name__)

if getattr(sys, "frozen", False):
    TEMPLATES_DIR = Path(sys._MEIPASS) / "bulletin_maker" / "ui" / "templates"
else:
    TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _on_closing(api: BulletinAPI) -> None:
    """Called when the window is about to close."""
    api.cleanup()


def main() -> None:
    """Launch the Bulletin Maker desktop application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    api = BulletinAPI()

    window = webview.create_window(
        title="Bulletin Maker — Ascension Lutheran Church",
        url=str(TEMPLATES_DIR / "index.html"),
        js_api=api,
        width=900,
        height=700,
        min_size=(800, 600),
    )

    api.set_window(window)
    window.events.closing += lambda: _on_closing(api)

    webview.start(debug=False)


if __name__ == "__main__":
    main()
