"""Day-name extraction and output filename construction."""

from __future__ import annotations

import re
from datetime import datetime


def extract_day_name(title: str) -> str:
    """Extract the liturgical day name from an S&S title.

    "Sunday, February 22, 2026 First Sunday in Lent, Year A"
    -> "First Sunday in Lent"
    """
    day_name = title
    date_match = re.search(r'\d{4}\s+(.+)', day_name)
    if date_match:
        day_name = date_match.group(1).strip()
    day_name = re.sub(r',?\s*Year\s+[ABC]$', '', day_name).strip()
    return day_name


def build_date_suffix(date_str: str, day_title: str) -> str:
    """Build the date + day portion of an output filename.

    Returns e.g. ``2026.03.01 - First Sunday in Lent Year A``.
    If the date is not a Sunday, the weekday is prepended.

    Args:
        date_str: "YYYY-MM-DD".
        day_title: The S&S day title.
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    date_dot = dt.strftime("%Y.%m.%d")

    year_match = re.search(r',?\s*Year\s+([ABC])$', day_title.strip())
    year_letter = year_match.group(1) if year_match else ""
    day_label = extract_day_name(day_title)

    if dt.weekday() != 6:  # 6 = Sunday
        weekday = dt.strftime("%A")
        day_label = f"{weekday} - {day_label}"

    if year_letter:
        day_label += " Year " + year_letter
    return f"{date_dot} - {day_label}"


def build_filename(doc_label: str, date_str: str, day_title: str) -> str:
    """Build a full output filename like
    ``Bulletin for Congregation - 2026.03.01 - First Sunday in Lent Year A.pdf``.
    """
    return f"{doc_label} - {build_date_suffix(date_str, day_title)}.pdf"
