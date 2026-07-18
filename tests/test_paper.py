"""Tests for paper-size presets."""

from __future__ import annotations

import pytest
from pypdf import PdfReader, PdfWriter

from bulletin_maker.exceptions import BulletinError
from bulletin_maker.renderer.paper import (
    DEFAULT_PAPER_KEY,
    PAPER_PRESETS,
    get_paper_preset,
)
from bulletin_maker.renderer.pdf_engine import impose_booklet


class TestPresets:

    def test_three_presets(self):
        assert set(PAPER_PRESETS) == {"legal_booklet", "letter_booklet", "a4_booklet"}

    def test_default_is_legal(self):
        preset = get_paper_preset(DEFAULT_PAPER_KEY)
        assert preset.half_page_width_pt == 504.0
        assert preset.page_height_pt == 612.0
        assert preset.flat_page_size == "Letter"

    def test_a4_geometry_in_points(self):
        preset = get_paper_preset("a4_booklet")
        assert round(preset.half_page_width_pt, 1) == 420.9  # A5 width
        assert round(preset.page_height_pt, 1) == 595.3      # A5 height

    def test_unknown_raises(self):
        with pytest.raises(BulletinError, match="Unknown paper size"):
            get_paper_preset("tabloid")


class TestImposeWithPresetGeometry:

    @pytest.mark.parametrize("key", sorted(PAPER_PRESETS))
    def test_sheet_is_double_width_of_preset(self, tmp_path, key):
        preset = get_paper_preset(key)
        writer = PdfWriter()
        for _ in range(4):
            writer.add_blank_page(width=preset.half_page_width_pt,
                                  height=preset.page_height_pt)
        seq = tmp_path / "seq.pdf"
        with open(seq, "wb") as f:
            writer.write(f)
        out = impose_booklet(
            seq, tmp_path / "booklet.pdf",
            half_page_width_pt=preset.half_page_width_pt,
            page_height_pt=preset.page_height_pt,
        )
        page = PdfReader(str(out)).pages[0]
        assert float(page.mediabox.width) == pytest.approx(preset.half_page_width_pt * 2)
        assert float(page.mediabox.height) == pytest.approx(preset.page_height_pt)
