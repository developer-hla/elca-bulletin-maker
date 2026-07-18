"""Day-content views shared by every UI adapter.

Builds the liturgical-text preset options and reading previews the
wizard shows, from a fetched DayContent.
"""

from __future__ import annotations

import re

from bulletin_maker.exceptions import ContentNotFoundError
from bulletin_maker.renderer.static_text import (
    AARONIC_BLESSING,
    CONFESSION_AND_FORGIVENESS,
    DISMISSAL_ENTRIES,
)
from bulletin_maker.renderer.text_utils import (
    clean_sns_html,
    group_psalm_verses,
    parse_dialog_html,
    preprocess_html,
)
from bulletin_maker.sns.models import DayContent, Reading

READING_SLOT_LABELS = {
    "first": "First Reading",
    "second": "Second Reading",
    "psalm": "Psalm",
    "gospel": "Gospel",
}


def _entries_to_dicts(entries) -> list:
    return [{"role": r.value, "text": t} for r, t in entries]


def build_liturgical_text_options(day: DayContent) -> dict:
    """Named preset options for the 5 variable liturgical texts.

    Each text has an ``options`` list of named presets (house customs,
    S&S weekly variants) and a ``default`` key. UIs render radio
    buttons from the options list.
    """
    sns_confession = _entries_to_dicts(
        parse_dialog_html(day.confession_html)
    ) if day.confession_html else []

    sns_dismissal = _entries_to_dicts(
        parse_dialog_html(day.dismissal_html)
    ) if day.dismissal_html else []

    return {
        "prayer_of_day": {
            "label": "Prayer of the Day",
            "type": "text",
            "default": "sns",
            "options": [
                {"key": "sns", "label": "This Week’s (S&S)",
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
                {"key": "sns", "label": "This Week’s (S&S)",
                 "data": sns_confession,
                 "disabled": not bool(sns_confession)},
            ],
        },
        "offering_prayer": {
            "label": "Offering Prayer",
            "type": "text",
            "default": "sns",
            "options": [
                {"key": "sns", "label": "This Week’s (S&S)",
                 "data": clean_sns_html(day.offering_prayer_html),
                 "disabled": not bool(day.offering_prayer_html)},
            ],
        },
        "prayer_after_communion": {
            "label": "Prayer After Communion",
            "type": "text",
            "default": "sns",
            "options": [
                {"key": "sns", "label": "This Week’s (S&S)",
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
                {"key": "sns", "label": "This Week’s (S&S)",
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
                {"key": "sns", "label": "This Week’s (S&S)",
                 "data": sns_dismissal,
                 "disabled": not bool(sns_dismissal)},
            ],
        },
    }


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


def _find_reading(day: DayContent, slot: str) -> Reading:
    target_label = READING_SLOT_LABELS.get(slot)
    if not target_label:
        raise ValueError(f"Unknown slot: {slot}")
    for r in day.readings:
        if r.label == target_label:
            return r
    raise ContentNotFoundError(f"No {target_label} found for this date.")


def build_reading_preview(day: DayContent, slot: str) -> dict:
    """Rendered-HTML preview of one reading for the wizard.

    Raises ValueError for an unknown slot and ContentNotFoundError when
    the day has no such reading.
    """
    reading = _find_reading(day, slot)
    if slot == "psalm":
        preview_html = _build_psalm_preview(reading.text_html)
    else:
        body = reading.text_html
        body = re.sub(r'^<div[^>]*>', '', body)
        body = re.sub(r'</div>\s*$', '', body)
        preview_html = preprocess_html(body)

    return {
        "label": reading.label,
        "citation": reading.citation,
        "intro": clean_sns_html(reading.intro),
        "preview_html": preview_html,
    }
