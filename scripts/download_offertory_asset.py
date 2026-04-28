"""Download the offertory hymn notation image (LS 97 'Come, Lord Jesus').

The offertory hymn is fixed every Sunday, so the image is bundled as a
static asset rather than fetched at runtime. Run this once to (re)create
src/bulletin_maker/renderer/assets/offertory.jpg.
"""
from __future__ import annotations

import sys
from pathlib import Path

from bulletin_maker.sns import SundaysClient
from bulletin_maker.sns.client import BASE


OFFERTORY_ATOM_CODE = "STANZA_0961_m"
ASSET_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "bulletin_maker" / "renderer" / "assets" / "offertory.jpg"
)


def main() -> int:
    with SundaysClient() as client:
        client.login()
        url = f"{BASE}/File/GetImage?atomCode={OFFERTORY_ATOM_CODE}"
        image_bytes = client.download_image(url)

    ASSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    ASSET_PATH.write_bytes(image_bytes)
    print(f"Saved {len(image_bytes)} bytes -> {ASSET_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
