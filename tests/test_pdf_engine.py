"""Tests for pdf_engine booklet imposition and page counting.

Pure pypdf — no Chromium required. Full rendered-layout assertions
live in test_layout_regression.py (marked ``layout``).
"""

from __future__ import annotations

import pytest
from pypdf import PdfReader, PdfWriter

from bulletin_maker.renderer.pdf_engine import (
    HALF_PAGE_WIDTH_PT,
    PAGE_HEIGHT_PT,
    count_pages,
    impose_booklet,
)


def _sequential_pdf(tmp_path, n: int):
    """Write an n-page blank PDF at bulletin half-page size."""
    writer = PdfWriter()
    for _ in range(n):
        writer.add_blank_page(width=HALF_PAGE_WIDTH_PT, height=PAGE_HEIGHT_PT)
    path = tmp_path / f"seq_{n}.pdf"
    with open(path, "wb") as f:
        writer.write(f)
    return path


class TestImposeBooklet:

    @pytest.mark.parametrize("n,expected_sheets", [
        (4, 2),    # exact booklet: 1 physical sheet, front+back
        (5, 4),    # pads to 8
        (8, 4),
        (15, 8),   # pads to 16 — the real bulletin shape
        (16, 8),
    ])
    def test_output_page_count(self, tmp_path, n, expected_sheets):
        seq = _sequential_pdf(tmp_path, n)
        out = impose_booklet(seq, tmp_path / "booklet.pdf")
        assert len(PdfReader(str(out)).pages) == expected_sheets

    def test_sheet_dimensions_are_legal_landscape(self, tmp_path):
        seq = _sequential_pdf(tmp_path, 4)
        out = impose_booklet(seq, tmp_path / "booklet.pdf")
        page = PdfReader(str(out)).pages[0]
        assert float(page.mediabox.width) == HALF_PAGE_WIDTH_PT * 2
        assert float(page.mediabox.height) == PAGE_HEIGHT_PT

    def test_single_page_pads_to_one_sheet(self, tmp_path):
        seq = _sequential_pdf(tmp_path, 1)
        out = impose_booklet(seq, tmp_path / "booklet.pdf")
        assert len(PdfReader(str(out)).pages) == 2  # front + back


class TestCountPages:

    def test_counts_pages(self, tmp_path):
        assert count_pages(_sequential_pdf(tmp_path, 3)) == 3

    def test_missing_file_returns_none(self, tmp_path):
        assert count_pages(tmp_path / "nope.pdf") is None
