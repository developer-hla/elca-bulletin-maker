#!/usr/bin/env python3
"""Generate Luther Rose app icons (.icns for macOS, .ico for Windows).

Uses Playwright to render an SVG at 1024x1024, then Pillow to resize
into all required icon sizes.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

# Output paths
UI_DIR = Path(__file__).resolve().parent.parent / "src" / "bulletin_maker" / "ui"
ICNS_PATH = UI_DIR / "icon.icns"
ICO_PATH = UI_DIR / "icon.ico"

# macOS .iconset sizes: (filename_base, pixel_size)
ICONSET_SIZES = [
    ("icon_16x16", 16),
    ("icon_16x16@2x", 32),
    ("icon_32x32", 32),
    ("icon_32x32@2x", 64),
    ("icon_64x64", 64),
    ("icon_64x64@2x", 128),
    ("icon_128x128", 128),
    ("icon_128x128@2x", 256),
    ("icon_256x256", 256),
    ("icon_256x256@2x", 512),
    ("icon_512x512", 512),
    ("icon_512x512@2x", 1024),
]

# Windows .ico sizes
ICO_SIZES = [16, 32, 48, 256]

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "bulletin_maker" / "ui" / "templates"
SVG_PATH = TEMPLATES_DIR / "luther-rose.svg"


def render_svg_to_png(output_path: Path) -> None:
    """Render the Luther Rose SVG to a 1024x1024 PNG using Playwright."""
    html = f"""\
<!DOCTYPE html>
<html>
<head><style>
* {{ margin: 0; padding: 0; }}
html, body {{ width: 1024px; height: 1024px; background: transparent; overflow: hidden; }}
</style></head>
<body>
<img src="file://{SVG_PATH}" width="1024" height="1024">
</body>
</html>"""

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        f.write(html)
        html_path = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": 1024, "height": 1024},
                device_scale_factor=1,
            )
            page.goto(f"file://{html_path}")
            page.wait_for_timeout(500)  # let SVG render fully
            page.screenshot(
                path=str(output_path),
                omit_background=True,
                clip={"x": 0, "y": 0, "width": 1024, "height": 1024},
            )
            browser.close()
    finally:
        Path(html_path).unlink(missing_ok=True)

    print(f"Rendered 1024x1024 PNG: {output_path}")


def create_iconset(source_png: Path, iconset_dir: Path) -> None:
    """Create a macOS .iconset directory with all required sizes."""
    iconset_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(source_png)

    for name, size in ICONSET_SIZES:
        resized = img.resize((size, size), Image.LANCZOS)
        resized.save(iconset_dir / f"{name}.png", "PNG")

    print(f"Created iconset with {len(ICONSET_SIZES)} sizes: {iconset_dir}")


def create_icns(iconset_dir: Path, output_path: Path) -> None:
    """Run iconutil to create a .icns file from an .iconset directory."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_path)],
        check=True,
    )
    print(f"Created .icns: {output_path}")


def create_ico(source_png: Path, output_path: Path) -> None:
    """Create a Windows .ico file with all required sizes."""
    img = Image.open(source_png).convert("RGBA")
    ico_images = [img.resize((s, s), Image.LANCZOS) for s in ICO_SIZES]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Save the largest size as base, append smaller sizes
    ico_images[-1].save(
        str(output_path),
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=ico_images[:-1],
    )
    print(f"Created .ico: {output_path}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        png_path = tmp / "icon_1024.png"
        iconset_dir = tmp / "icon.iconset"

        # Step 1: Render SVG to 1024x1024 PNG
        render_svg_to_png(png_path)

        # Step 2: Create macOS .iconset and .icns
        create_iconset(png_path, iconset_dir)
        create_icns(iconset_dir, ICNS_PATH)

        # Step 3: Create Windows .ico
        create_ico(png_path, ICO_PATH)

    print("\nDone! Icon files:")
    print(f"  macOS: {ICNS_PATH}")
    print(f"  Windows: {ICO_PATH}")


if __name__ == "__main__":
    main()
