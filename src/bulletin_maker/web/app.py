"""Entry point — run the Bulletin Maker web app locally.

`bulletin-maker` starts the FastAPI server on localhost and opens the
wizard in the default browser. First run downloads Chromium (the PDF
renderer) automatically.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from bulletin_maker.web.server import create_app

DEFAULT_PORT = 8355


def _ensure_chromium() -> None:
    """Download Playwright's Chromium on first run."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        executable = Path(p.chromium.executable_path)
    if executable.exists():
        return
    print("First run: downloading the PDF renderer (Chromium, ~100 MB)...")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )


def _pick_port() -> int:
    """Use the default port when free, else an OS-assigned one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", DEFAULT_PORT))
            return DEFAULT_PORT
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    _ensure_chromium()
    port = _pick_port()
    url = f"http://127.0.0.1:{port}"
    print(f"Bulletin Maker is running at {url}")
    print("Keep this window open while you work; press Ctrl+C to quit.")
    threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
