"""Playwright-based PDF rendering engine with auto-shrink support."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# When running as a PyInstaller bundle, tell Playwright where to find
# the bundled Chromium browser (installed with PLAYWRIGHT_BROWSERS_PATH=0).
if getattr(sys, "frozen", False):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

# Page dimensions in points (72pt = 1in)
HALF_PAGE_WIDTH_PT = 504.0  # 7 inches
PAGE_HEIGHT_PT = 612.0      # 8.5 inches

AUTO_SHRINK_SCALES = (0.95, 0.90, 0.85, 0.80)

# ── Page margin presets ──────────────────────────────────────────────
# Single source of truth for all document types.

MARGINS_DEFAULT = {
    "top": "0.25in",
    "bottom": "0.5in",
    "left": "0.438in",
    "right": "0.438in",
}

MARGINS_PULPIT = {
    "top": "0.85in",
    "bottom": "0.4in",
    "left": "0.5in",
    "right": "0.5in",
}

MARGINS_BULLETIN = {
    "top": "0.3in",
    "bottom": "0.35in",
    "left": "0.35in",
    "right": "0.35in",
}


def render_to_pdf(
    html_string: str,
    output_path: Path,
    *,
    margins: dict | None = None,
    display_footer: bool = False,
    header_left: str = "",
    header_right: str = "",
    pulpit_header: bool = False,
    scale: float = 1.0,
    page_size: str | dict = "Letter",
) -> Path:
    """Render an HTML string to PDF via headless Chromium (Playwright).

    Args:
        html_string: Complete HTML document string.
        output_path: Where to write the PDF (suffix forced to .pdf).
        margins: Dict with top/bottom/left/right as CSS length strings.
        display_footer: Whether to show page numbers in footer.
        header_left: Left-side header text (for pulpit docs).
        header_right: Right-side header text.
        pulpit_header: If True, use the pulpit-style header with
            Leader: field and underline.
        scale: Page rendering scale (0.1-2.0). Use < 1.0 to shrink.
        page_size: Page format string (e.g. "Letter") or dict with
            "width" and "height" CSS lengths (e.g. {"width": "7in",
            "height": "8.5in"}).

    Returns:
        Path to the generated PDF.
    """
    from playwright.sync_api import sync_playwright

    output_path = Path(output_path).with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    margins = margins or MARGINS_DEFAULT

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_string, wait_until="networkidle")

        pdf_opts = {
            "path": str(output_path),
            "print_background": True,
            "margin": margins,
            "scale": scale,
        }

        if isinstance(page_size, dict):
            pdf_opts["width"] = page_size["width"]
            pdf_opts["height"] = page_size["height"]
        else:
            pdf_opts["format"] = page_size

        if display_footer or pulpit_header:
            pdf_opts["display_header_footer"] = True

            if pulpit_header:
                pdf_opts["header_template"] = (
                    '<div style="font-size: 10pt; width: 100%; '
                    'padding: 0 0.5in 4pt 0.5in; '
                    'border-bottom: 1.5pt solid black; '
                    'font-family: Cambria, Georgia, serif;">'
                    '<div style="display: flex; justify-content: space-between; '
                    'align-items: baseline;">'
                    f'<span style="font-weight: bold; font-size: 13pt;">'
                    f'{header_left}</span>'
                    '<span style="font-size: 10pt;">Leader: '
                    '<span style="display: inline-block; width: 100pt; '
                    'border-bottom: 1pt solid black;">&nbsp;</span></span>'
                    '</div>'
                    '</div>'
                )
            elif header_left or header_right:
                pdf_opts["header_template"] = (
                    '<div style="font-size: 9pt; width: 100%; display: flex; '
                    'justify-content: space-between; padding: 0 0.5in;">'
                    f'<span>{header_left}</span>'
                    f'<span>{header_right}</span>'
                    '</div>'
                )
            else:
                pdf_opts["header_template"] = "<span></span>"

            pdf_opts["footer_template"] = (
                '<div style="font-size: 12pt; text-align: center; width: 100%;">'
                '<span class="pageNumber"></span>'
                '</div>'
            )

        page.pdf(**pdf_opts)
        browser.close()

    return output_path


def count_pages(pdf_path: Path) -> int | None:
    """Count pages in a PDF file. Returns None on failure."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf_path)).pages)
    except ImportError:
        return None
    except (OSError, ValueError):
        logger.warning("Could not count pages in %s", pdf_path)
        return None


def impose_booklet(input_pdf: Path, output_pdf: Path) -> Path:
    """Rearrange sequential half-pages into saddle-stitched booklet spreads.

    Takes a PDF of sequential 7"x8.5" pages and produces legal-landscape
    (14"x8.5") sheets with pages arranged for duplex printing and folding.

    Booklet imposition for N pages (padded to multiple of 4):
      Sheet i front: [N-2i, 2i+1]  (left, right)
      Sheet i back:  [2i+2, N-2i-1]

    Args:
        input_pdf: Path to the sequential half-page PDF.
        output_pdf: Where to write the imposed booklet PDF.

    Returns:
        Path to the imposed PDF.
    """
    from pypdf import PdfReader, PdfWriter, PageObject, Transformation

    reader = PdfReader(str(input_pdf))
    n = len(reader.pages)

    # Pad to multiple of 4
    padded = n + (4 - n % 4) % 4

    half_w = HALF_PAGE_WIDTH_PT
    page_h = PAGE_HEIGHT_PT
    full_w = half_w * 2

    writer = PdfWriter()

    num_sheets = padded // 2
    for i in range(0, num_sheets, 2):
        sheet_idx = i // 2
        # Front side: left = page (padded - 2*sheet_idx - 1), right = page (2*sheet_idx)
        left_idx = padded - 2 * sheet_idx - 1
        right_idx = 2 * sheet_idx

        front = PageObject.create_blank_page(width=full_w, height=page_h)
        if left_idx < n:
            front.merge_transformed_page(
                reader.pages[left_idx],
                Transformation().translate(tx=0, ty=0),
            )
        if right_idx < n:
            front.merge_transformed_page(
                reader.pages[right_idx],
                Transformation().translate(tx=half_w, ty=0),
            )
        writer.add_page(front)

        # Back side: left = page (2*sheet_idx + 1), right = page (padded - 2*sheet_idx - 2)
        back_left_idx = 2 * sheet_idx + 1
        back_right_idx = padded - 2 * sheet_idx - 2

        back = PageObject.create_blank_page(width=full_w, height=page_h)
        if back_left_idx < n:
            back.merge_transformed_page(
                reader.pages[back_left_idx],
                Transformation().translate(tx=0, ty=0),
            )
        if back_right_idx < n:
            back.merge_transformed_page(
                reader.pages[back_right_idx],
                Transformation().translate(tx=half_w, ty=0),
            )
        writer.add_page(back)

    output_pdf = Path(output_pdf).with_suffix(".pdf")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with open(output_pdf, "wb") as f:
        writer.write(f)

    logger.info("Booklet imposed: %d pages -> %d sheets, saved %s",
                n, padded // 4, output_pdf)
    return output_pdf


def render_with_shrink(
    html_string: str,
    output_path: Path,
    *,
    margins: dict | None = None,
    max_pages: int = 2,
    header_left: str = "",
    header_right: str = "",
    pulpit_header: bool = False,
) -> Path:
    """Render HTML to PDF, auto-shrinking if it exceeds max_pages.

    Uses Playwright's scale parameter (proportional shrink of entire page)
    rather than CSS overrides, so all elements shrink uniformly.
    """
    output_path = Path(output_path).with_suffix(".pdf")

    result = render_to_pdf(
        html_string, output_path,
        margins=margins, display_footer=True,
        header_left=header_left, header_right=header_right,
        pulpit_header=pulpit_header,
    )

    pages = count_pages(result)
    if pages is None or pages <= max_pages:
        return result

    for scale in AUTO_SHRINK_SCALES:
        result = render_to_pdf(
            html_string, output_path,
            margins=margins, display_footer=True,
            header_left=header_left, header_right=header_right,
            pulpit_header=pulpit_header,
            scale=scale,
        )
        pages = count_pages(result)
        if pages is not None and pages <= max_pages:
            logger.info("Auto-shrink: scale=%.2f gave %d pages", scale, pages)
            return result

    return result
