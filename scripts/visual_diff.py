"""Visual comparison of generated PDFs against reference examples.

Renders each PDF page to an image, creates side-by-side composites,
and generates pixel-diff images highlighting any differences.

Usage:
    source venv/bin/activate
    python scripts/visual_diff.py

Outputs to output/diff/:
    scripture_p1_compare.png  — side-by-side page 1
    scripture_p1_diff.png     — pixel diff (red = differences)
    prayers_p1_compare.png    — side-by-side page 1
    prayers_p1_diff.png       — pixel diff
    ...
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz  # pymupdf
from PIL import Image, ImageChops, ImageDraw

EXAMPLE_DIR = Path("examples/-02-2026 February/ASCENSION -- 2026.02.22 LENT 1A")
OUTPUT_DIR = Path("output")
DIFF_DIR = OUTPUT_DIR / "diff"

PAIRS = [
    {
        "name": "scripture",
        "ours": OUTPUT_DIR / "Pulpit SCRIPTURE 8.5 x 11.pdf",  # now generated as PDF directly
        "ref": EXAMPLE_DIR / "ASCENSION -- 2026.02.22 LENT 1A - Pulpit SCRIPTURE 8.5 x 11.pdf",
    },
    {
        "name": "prayers",
        "ours": OUTPUT_DIR / "Pulpit PRAYERS + NICENE 8.5 x 11.pdf",  # now generated as PDF directly
        "ref": EXAMPLE_DIR / "ASCENSION -- 2026.02.22 LENT 1A - Pulpit PRAYERS + APOSTLES 8.5 x 11.pdf",
    },
]

DPI = 200  # render resolution


def pdf_to_images(pdf_path: Path, dpi: int = DPI) -> list[Image.Image]:
    """Render each page of a PDF to a PIL Image."""
    doc = fitz.open(str(pdf_path))
    images = []
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def make_side_by_side(ours: Image.Image, ref: Image.Image, label: str) -> Image.Image:
    """Create a side-by-side comparison image with labels."""
    gap = 20
    label_height = 30

    # Resize to same height if needed
    h = max(ours.height, ref.height)
    if ours.height != h:
        ours = ours.resize((int(ours.width * h / ours.height), h))
    if ref.height != h:
        ref = ref.resize((int(ref.width * h / ref.height), h))

    w = ours.width + gap + ref.width
    composite = Image.new("RGB", (w, h + label_height), (255, 255, 255))

    # Draw labels
    draw = ImageDraw.Draw(composite)
    draw.text((ours.width // 2 - 30, 4), "OURS", fill=(0, 0, 200))
    draw.text((ours.width + gap + ref.width // 2 - 40, 4), "REFERENCE", fill=(0, 150, 0))

    composite.paste(ours, (0, label_height))
    composite.paste(ref, (ours.width + gap, label_height))

    # Draw separator line
    draw.rectangle(
        [ours.width + 2, label_height, ours.width + gap - 3, h + label_height - 1],
        fill=(200, 200, 200),
    )

    return composite


def make_diff(ours: Image.Image, ref: Image.Image) -> Image.Image:
    """Create a diff image highlighting pixel differences in red.

    Uses PIL channel operations instead of per-pixel Python loops.
    """
    # Resize to same dimensions
    w = max(ours.width, ref.width)
    h = max(ours.height, ref.height)
    ours_r = ours.resize((w, h))
    ref_r = ref.resize((w, h))

    diff = ImageChops.difference(ours_r, ref_r)

    # Build a mask: pixel is "different" when sum of RGB channels > 30
    r, g, b = diff.split()
    # Add channels pairwise (clamped at 255), then threshold
    channel_sum = ImageChops.add(ImageChops.add(r, g), b)
    mask = channel_sum.point(lambda v: 255 if v > 30 else 0)

    # Red overlay for changed pixels
    red = Image.new("RGB", (w, h), (255, 80, 80))

    # Composite: red where different, reference where same
    return Image.composite(red, ref_r, mask)


def main():
    DIFF_DIR.mkdir(parents=True, exist_ok=True)

    for pair in PAIRS:
        name = pair["name"]
        ours_path = pair["ours"]
        ref_path = pair["ref"]

        if not ours_path.exists():
            print(f"SKIP {name}: {ours_path} not found (run generate_test.py first)")
            continue
        if not ref_path.exists():
            print(f"SKIP {name}: {ref_path} not found")
            continue

        print(f"\n{'='*50}")
        print(f"Comparing: {name}")
        print(f"{'='*50}")

        ours_pages = pdf_to_images(ours_path)
        ref_pages = pdf_to_images(ref_path)

        max_pages = max(len(ours_pages), len(ref_pages))
        print(f"  Ours: {len(ours_pages)} page(s), Ref: {len(ref_pages)} page(s)")

        for i in range(max_pages):
            page_num = i + 1

            if i < len(ours_pages) and i < len(ref_pages):
                # Both have this page — compare
                compare = make_side_by_side(ours_pages[i], ref_pages[i], name)
                compare_path = DIFF_DIR / f"{name}_p{page_num}_compare.png"
                compare.save(str(compare_path))
                print(f"  Saved: {compare_path}")

                diff = make_diff(ours_pages[i], ref_pages[i])
                diff_path = DIFF_DIR / f"{name}_p{page_num}_diff.png"
                diff.save(str(diff_path))
                print(f"  Saved: {diff_path}")
            elif i < len(ours_pages):
                # Only ours has this page
                path = DIFF_DIR / f"{name}_p{page_num}_ours_only.png"
                ours_pages[i].save(str(path))
                print(f"  Saved (ours only): {path}")
            else:
                # Only ref has this page
                path = DIFF_DIR / f"{name}_p{page_num}_ref_only.png"
                ref_pages[i].save(str(path))
                print(f"  Saved (ref only): {path}")

    print(f"\nAll comparisons saved to: {DIFF_DIR}")


if __name__ == "__main__":
    main()
