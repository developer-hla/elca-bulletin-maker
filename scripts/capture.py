"""
Phase 1 — API Discovery: Playwright network capture script.

Opens a visible browser to sundaysandseasons.com and logs all network
requests/responses to captured_requests.json.

Usage:
    source venv/bin/activate
    python capture.py

Browse the site manually — log in, view a few Sundays, look up some hymns.
When done, close the browser window. The script saves automatically.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode
from playwright.sync_api import sync_playwright

OUTPUT = Path(__file__).parent / "captured_requests.json"
TARGET_DOMAIN = "sundaysandseasons.com"
SENSITIVE_FIELDS = {"Password", "password", "UserName", "username"}

captured = []


def strip_credentials(post_data: str | None) -> str | None:
    """Replace sensitive field values in POST data with [REDACTED]."""
    if not post_data:
        return post_data
    try:
        params = parse_qs(post_data, keep_blank_values=True)
        redacted = False
        for key in list(params.keys()):
            if key in SENSITIVE_FIELDS:
                params[key] = ["[REDACTED]"]
                redacted = True
        if redacted:
            return urlencode(params, doseq=True)
    except Exception:
        pass
    return post_data


def on_response(response):
    request = response.request
    url = request.url

    # Only capture requests to the target domain
    if TARGET_DOMAIN not in url:
        return

    entry = {
        "timestamp": time.time(),
        "method": request.method,
        "url": url,
        "request_headers": dict(request.headers),
        "post_data": strip_credentials(request.post_data),
        "status": response.status,
        "response_headers": dict(response.headers),
        "response_body": None,
    }

    # Try to capture response body (skip binary/large responses)
    content_type = response.headers.get("content-type", "")
    if any(t in content_type for t in ["json", "html", "text", "xml", "javascript"]):
        try:
            entry["response_body"] = response.text()
        except Exception:
            entry["response_body"] = "<could not read body>"

    captured.append(entry)
    print(f"  [{response.status}] {request.method} {url[:120]}")


def main():
    print("=" * 60)
    print("Sundays & Seasons — Network Capture")
    print("=" * 60)
    print()
    print("A browser window will open. Please:")
    print("  1. Log in to sundaysandseasons.com")
    print("  2. Navigate to a few different Sundays/dates")
    print("  3. Look up a couple of hymns by number")
    print("  4. Close the browser when done")
    print()
    print(f"All traffic will be saved to: {OUTPUT.name}")
    print("-" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.on("response", on_response)
        page.goto("https://www.sundaysandseasons.com/")

        # Wait until the user closes the browser
        try:
            while page.url:
                page.wait_for_timeout(1000)
        except Exception:
            pass

        browser.close()

    # Save captured data
    with open(OUTPUT, "w") as f:
        json.dump(captured, f, indent=2, default=str)

    print()
    print("=" * 60)
    print(f"Done! Captured {len(captured)} requests.")
    print(f"Saved to {OUTPUT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
