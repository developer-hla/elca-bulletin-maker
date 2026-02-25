"""Document rendering package — generates print-ready PDFs.

Uses HTML/CSS + Playwright (headless Chromium) for PDF generation.
"""

from __future__ import annotations

from bulletin_maker.renderer.html_renderer import (
    generate_bulletin,
    generate_large_print,
    generate_pulpit_prayers,
    generate_pulpit_scripture,
)

__all__ = [
    "generate_bulletin",
    "generate_pulpit_scripture",
    "generate_pulpit_prayers",
    "generate_large_print",
]
