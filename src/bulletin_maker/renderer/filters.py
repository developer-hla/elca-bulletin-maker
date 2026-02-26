"""Jinja2 template filters and environment setup."""

from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

if getattr(sys, "frozen", False):
    TEMPLATE_DIR = Path(sys._MEIPASS) / "bulletin_maker" / "renderer" / "templates" / "html"
else:
    TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "html"


def nl2br(text: str) -> str:
    """Convert newlines to <br> tags."""
    if not text:
        return ""
    return text.replace("\n", "<br>\n")


def hymn_text(text: str) -> str:
    """Format hymn verse text for HTML: tabs -> em-spaces, newlines -> <br>."""
    if not text:
        return ""
    text = text.replace("\t", "&emsp;")
    text = text.replace("\n", "<br>\n")
    return text


def creed_line(text: str) -> str:
    """Format creed stanza: leading spaces -> indent, newlines -> <br>."""
    if not text:
        return ""
    lines = text.split("\n")
    result = []
    for line in lines:
        if line.startswith("  "):
            result.append("&emsp;&emsp;" + line.strip())
        else:
            result.append(line)
    return "<br>\n".join(result)


def setup_jinja_env() -> Environment:
    """Create and configure the Jinja2 template environment."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,  # Not a web server — generating PDF via Playwright
    )
    env.filters["nl2br"] = nl2br
    env.filters["hymn_text"] = hymn_text
    env.filters["creed_line"] = creed_line
    return env
