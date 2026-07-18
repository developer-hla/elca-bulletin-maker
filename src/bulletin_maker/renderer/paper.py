"""Paper-size presets — a bounded output-geometry choice.

Each preset fixes the booklet half-page geometry (the bulletin renders
sequential half-pages, then imposes them two-up onto landscape sheets)
and the page format for the flat documents (large print, leader guide,
pulpit sheets).

legal_booklet is the shipped default and the only preset pinned by the
layout-regression harness; the others are validated as
generates-successfully smoke cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from bulletin_maker.exceptions import BulletinError

_MM_TO_PT = 72 / 25.4


@dataclass(frozen=True)
class PaperPreset:
    key: str
    label: str
    half_page_css: dict        # {"width": ..., "height": ...} CSS lengths
    half_page_width_pt: float  # imposition geometry (72pt = 1in)
    page_height_pt: float
    flat_page_size: str        # Playwright format for non-booklet docs


PAPER_PRESETS: dict = {
    p.key: p
    for p in (
        PaperPreset(
            key="legal_booklet",
            label="Legal booklet (7×8.5in halves) + Letter",
            half_page_css={"width": "7in", "height": "8.5in"},
            half_page_width_pt=504.0,
            page_height_pt=612.0,
            flat_page_size="Letter",
        ),
        PaperPreset(
            key="letter_booklet",
            label="Letter booklet (5.5×8.5in halves) + Letter",
            half_page_css={"width": "5.5in", "height": "8.5in"},
            half_page_width_pt=396.0,
            page_height_pt=612.0,
            flat_page_size="Letter",
        ),
        PaperPreset(
            key="a4_booklet",
            label="A4 booklet (A5 halves) + A4",
            half_page_css={"width": "148.5mm", "height": "210mm"},
            half_page_width_pt=148.5 * _MM_TO_PT,
            page_height_pt=210 * _MM_TO_PT,
            flat_page_size="A4",
        ),
    )
}

DEFAULT_PAPER_KEY = "legal_booklet"


def get_paper_preset(key: str) -> PaperPreset:
    """Look up a paper preset by profile key."""
    try:
        return PAPER_PRESETS[key]
    except KeyError:
        raise BulletinError(
            f"Unknown paper size: {key!r}. "
            f"Valid sizes: {', '.join(sorted(PAPER_PRESETS))}"
        ) from None
