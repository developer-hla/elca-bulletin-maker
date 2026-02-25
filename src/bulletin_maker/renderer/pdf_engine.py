"""Playwright-based PDF rendering engine with auto-shrink support."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


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

    Returns:
        Path to the generated PDF.
    """
    from playwright.sync_api import sync_playwright

    output_path = Path(output_path).with_suffix(".pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    default_margins = {
        "top": "0.25in",
        "bottom": "0.5in",
        "left": "0.438in",
        "right": "0.438in",
    }
    margins = margins or default_margins

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_string, wait_until="networkidle")

        pdf_opts = {
            "path": str(output_path),
            "format": "Letter",
            "print_background": True,
            "margin": margins,
            "scale": scale,
        }

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
    except Exception:
        return None


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

    for scale in (0.95, 0.90, 0.85, 0.80):
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
