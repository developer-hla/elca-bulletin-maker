"""Desktop UI package — pywebview-based bulletin wizard."""

from __future__ import annotations


def launch() -> None:
    """Launch the bulletin maker desktop application."""
    from bulletin_maker.ui.app import main

    main()
