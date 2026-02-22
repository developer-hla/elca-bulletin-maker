"""Data models for Sundays & Seasons content."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Reading:
    label: str        # e.g. "First Reading", "Psalm", "Gospel"
    citation: str     # e.g. "Genesis 2:15-17; 3:1-7"
    intro: str        # italic intro paragraph
    text_html: str    # raw HTML of the reading text


@dataclass
class DayContent:
    date: str
    title: str                          # e.g. "First Sunday in Lent, Year A"
    introduction: str
    confession_html: str
    prayer_of_the_day_html: str
    gospel_acclamation: str
    readings: list[Reading] = field(default_factory=list)
    raw_html: str = ""                  # full rightpanel HTML for fallback


@dataclass
class HymnResult:
    atom_id: str
    title: str
    hymn_numbers: str = ""              # e.g. "ELW 504, TFF 133, LBW 229"
    harmony_atom_id: str = ""           # atomId for harmony download
    melody_atom_id: str = ""            # atomId for melody download
    words_atom_id: str = ""             # atomId for words download
    harmony_image_url: str = ""
    melody_image_url: str = ""
    atom_code: str = ""
    copyright_html: str = ""
