"""Layout regression harness — renders real PDFs from a recorded S&S day.

Marked ``layout`` and excluded from the default run (slow, needs
Chromium). Run with:

    venv/bin/python -m pytest tests/ -m layout -v

Assertions pin page counts and which page key liturgical anchors land
on. If you change layout INTENTIONALLY, update the pinned numbers here.
The fixture renders with no S&S client and no cover image, so counts
differ slightly from production output but are fully deterministic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pypdf import PdfReader

from bulletin_maker.renderer import (
    generate_bulletin,
    generate_large_print,
    generate_leader_guide,
    generate_pulpit_prayers,
    generate_pulpit_scripture,
)
from bulletin_maker.renderer.season import detect_season, fill_seasonal_defaults
from bulletin_maker.sns.models import DayContent, HymnLyrics, Reading, ServiceConfig

pytestmark = pytest.mark.layout

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures" / "day_content" / "lectionary16_2026-07-19.json"
)

# ── Pinned expectations (update deliberately on layout changes) ──────
BULLETIN_SEQ_PAGES = 15
BULLETIN_IMPOSED_PAGES = 8
LARGE_PRINT_PAGES = 17
LEADER_GUIDE_PAGES = 19
PULPIT_MAX_PAGES = 2


def _load_fixture() -> tuple[DayContent, dict[str, HymnLyrics]]:
    fx = json.loads(FIXTURE.read_text())
    day_data = dict(fx["day"])
    day_data["readings"] = [Reading(**r) for r in day_data["readings"]]
    day = DayContent(**day_data)
    hymns = {slot: HymnLyrics(**data) for slot, data in fx["hymns"].items()}
    return day, hymns


def _make_config(hymns: dict[str, HymnLyrics]) -> ServiceConfig:
    return ServiceConfig(
        date="2026-07-19",
        date_display="July 19, 2026",
        gathering_hymn=hymns["gathering"],
        sermon_hymn=hymns["sermon"],
        communion_hymn=hymns["communion"],
        sending_hymn=hymns["sending"],
        prelude_title="All Glory Be to God on High",
        prelude_composer="Johann Pachelbel",
        offertory_title="Seek Ye First",
        offertory_composer="Karen Lafferty",
        postlude_title="Savior, Again to Your Dear Name",
    )


def _page_texts(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [re.sub(r"\s+", " ", (p.extract_text() or "")) for p in reader.pages]


def _page_of(pages: list[str], needle: str) -> int | None:
    for i, text in enumerate(pages):
        if needle.lower() in text.lower():
            return i + 1
    return None


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """Render all five documents once for the module."""
    out = tmp_path_factory.mktemp("layout")
    day, hymns = _load_fixture()
    config = _make_config(hymns)
    season = detect_season(day.title)
    fill_seasonal_defaults(config, season)

    bulletin_path, creed_page = generate_bulletin(
        day, config, out / "bulletin.pdf", season=season,
        keep_intermediates=True,
    )
    seq_path = next(out.glob(".*_sequential.pdf"))
    adjust_meta = json.loads(
        (out / ".bulletin_debug" / "adjust_meta.json").read_text()
    )
    return {
        "out": out,
        "creed_page": creed_page,
        "bulletin": bulletin_path,
        "seq_pages": _page_texts(seq_path),
        "adjust_meta": adjust_meta,
        "large_print": generate_large_print(
            day, config, out / "lp.pdf", season=season),
        "leader_guide": generate_leader_guide(
            day, config, out / "lg.pdf", season=season),
        "pulpit_prayers": generate_pulpit_prayers(
            day, "July 19, 2026", creed_type="apostles",
            creed_page_num=creed_page, output_path=out / "pp.pdf"),
        "pulpit_scripture": generate_pulpit_scripture(
            day, "July 19, 2026", out / "ps.pdf", config=config),
    }


class TestBulletinLayout:

    def test_sequential_page_count(self, rendered):
        assert len(rendered["seq_pages"]) == BULLETIN_SEQ_PAGES

    def test_imposed_page_count(self, rendered):
        assert len(PdfReader(str(rendered["bulletin"])).pages) == BULLETIN_IMPOSED_PAGES

    def test_booklet_has_at_most_one_blank(self, rendered):
        assert rendered["adjust_meta"]["final_blanks"] <= 1

    def test_greeting_and_kyrie_share_a_page(self, rendered):
        pages = rendered["seq_pages"]
        greeting = _page_of(pages, "communion of the Holy Spirit")
        kyrie = _page_of(pages, "*KYRIE")
        assert greeting is not None and greeting == kyrie

    def test_creed_does_not_split(self, rendered):
        pages = rendered["seq_pages"]
        heading = _page_of(pages, "APOSTLES CREED")
        ending = _page_of(pages, "life everlasting")
        assert heading is not None and heading == ending

    def test_creed_page_matches_find_creed_page(self, rendered):
        pages = rendered["seq_pages"]
        assert rendered["creed_page"] == _page_of(pages, "APOSTLES CREED")

    def test_prayer_of_the_day_has_heading_and_body_together(self, rendered):
        pages = rendered["seq_pages"]
        heading = _page_of(pages, "PRAYER OF THE DAY")
        assert heading is not None
        assert "amen" in pages[heading - 1].lower()

    def test_cover_is_first_imposed_sheet(self, rendered):
        imposed = _page_texts(rendered["bulletin"])
        assert "Ascension Lutheran Church" in imposed[0]


class TestLargeFormatLayout:

    def test_large_print_page_count(self, rendered):
        assert len(PdfReader(str(rendered["large_print"])).pages) == LARGE_PRINT_PAGES

    def test_leader_guide_page_count(self, rendered):
        assert len(PdfReader(str(rendered["leader_guide"])).pages) == LEADER_GUIDE_PAGES

    def test_large_print_has_hymn_lyrics(self, rendered):
        pages = _page_texts(rendered["large_print"])
        assert _page_of(pages, "GATHERING HYMN: ELW 736") is not None

    def test_leader_guide_labeled_on_cover(self, rendered):
        pages = _page_texts(rendered["leader_guide"])
        assert "Leader Guide" in pages[0]


class TestPulpitLayout:

    def test_pulpit_prayers_fits_front_back(self, rendered):
        assert len(PdfReader(str(rendered["pulpit_prayers"])).pages) <= PULPIT_MAX_PAGES

    def test_pulpit_scripture_fits_front_back(self, rendered):
        assert len(PdfReader(str(rendered["pulpit_scripture"])).pages) <= PULPIT_MAX_PAGES

    def test_pulpit_prayers_references_creed_page(self, rendered):
        pages = _page_texts(rendered["pulpit_prayers"])
        assert f"page {rendered['creed_page']}" in pages[0]
