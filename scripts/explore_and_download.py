"""Explore S&S Library tree and download missing Setting Two images."""
from __future__ import annotations

import json
import os
import re
import sys
import time

import httpx

BASE = "https://members.sundaysandseasons.com"

# ── Auth ──────────────────────────────────────────────────────────────────

def create_client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=30.0,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    )


def login(client: httpx.Client, username: str, password: str) -> None:
    resp = client.get(f"{BASE}/Account/Login")
    resp.raise_for_status()
    token_match = re.search(
        r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', resp.text
    )
    if not token_match:
        raise RuntimeError("Could not find CSRF token on login page")
    token = token_match.group(1)
    resp = client.post(
        f"{BASE}/Account/Login",
        data={
            "__RequestVerificationToken": token,
            "UserName": username,
            "Password": password,
        },
    )
    resp.raise_for_status()
    if "Welcome back" in resp.text or "/Account/LogOff" in resp.text or "/Planner" in resp.text:
        print("Logged in successfully.")
    else:
        raise RuntimeError("Login may have failed — unexpected response.")


# ── Task 1: Explore Library Tree ─────────────────────────────────────────

def parse_children_html(html: str) -> list[dict]:
    """Parse the HTML response from /Library/_Children into a list of nodes."""
    children = []

    # Split on <li class="library_node"> boundaries
    # Each <li> contains: data-ajax-url (optional), title div, actions div, and <ul> children indicator
    li_blocks = re.split(r'<li\s+class="library_node"', html)

    for block in li_blocks[1:]:  # skip first empty split
        node = {}

        # Extract atomId from data-ajax-url
        ajax_match = re.search(r'data-ajax-url="/Library/_Children\?parentAtomId=(\d+)"', block)
        node["atomId"] = int(ajax_match.group(1)) if ajax_match else None

        # Extract title text
        title_match = re.search(
            r'<div[^>]*class="[^"]*title[^"]*"[^>]*>\s*(.*?)\s*</div>',
            block, re.DOTALL,
        )
        name = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else "???"
        node["name"] = name

        # Extract type name
        type_match = re.search(r'data-type-name="([^"]*)"', block)
        node["typeName"] = type_match.group(1) if type_match else ""

        # Extract atom codes from action links
        codes = re.findall(r'data-atom-code="([^"]+)"', block)
        node["atomCode"] = codes[0] if codes else ""

        # Has children?
        node["hasChildren"] = "has-children" in block

        # Has triangle? (folder indicator)
        node["isLeaf"] = "no-triangle" in block or not node["hasChildren"]

        children.append(node)

    return children


def get_children(client: httpx.Client, parent_atom_id: int) -> list[dict]:
    """GET /Library/_Children?parentAtomId={id} and parse HTML response."""
    url = f"{BASE}/Library/_Children?parentAtomId={parent_atom_id}"
    resp = client.get(url)
    resp.raise_for_status()
    return parse_children_html(resp.text)


def explore_tree(client: httpx.Client, parent_id: int, indent: int = 0,
                 max_depth: int = 4) -> list[dict]:
    """Recursively explore and print the library tree."""
    children = get_children(client, parent_id)
    result = []

    for child in children:
        prefix = "  " * indent
        name = child["name"]
        atom_id = child["atomId"]
        atom_code = child["atomCode"]
        type_name = child["typeName"]
        has_children = child["hasChildren"]

        extras = []
        if atom_id:
            extras.append(f"atomId={atom_id}")
        if atom_code:
            extras.append(f"atomCode={atom_code}")
        if type_name:
            extras.append(f"type={type_name}")

        suffix = f" [{', '.join(extras)}]" if extras else ""
        leaf = " (leaf)" if child["isLeaf"] else ""
        print(f"{prefix}- {name}{suffix}{leaf}")

        child_tree = []
        if has_children and atom_id and indent < max_depth:
            time.sleep(0.3)
            child_tree = explore_tree(client, atom_id, indent + 1, max_depth)

        result.append({
            "name": name,
            "atomId": atom_id,
            "atomCode": atom_code,
            "typeName": type_name,
            "hasChildren": has_children,
            "isLeaf": child["isLeaf"],
            "children": child_tree,
        })

    return result


def explore_holy_communion(client: httpx.Client) -> list[dict]:
    """Explore all children of Holy Communion (atomId=26026)."""
    print("\n" + "=" * 70)
    print("EXPLORING: Holy Communion (atomId=26026) — All siblings of Setting Two")
    print("=" * 70 + "\n")
    tree = explore_tree(client, 26026, indent=0, max_depth=4)

    # Save full tree as JSON for reference
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    out_path = os.path.join(data_dir, "holy_communion_tree.json")
    with open(out_path, "w") as f:
        json.dump(tree, f, indent=2, default=str)
    print(f"\nFull tree saved to: {out_path}")
    return tree


# ── Task 2: Download Missing Images ─────────────────────────────────────

ASSETS_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "src",
    "bulletin_maker",
    "renderer",
    "assets",
    "setting_two",
))

IMAGES_TO_DOWNLOAD = [
    # (atom_code, save_as)
    ("elw_hc2_accltone_m", "acclamation_tone"),
    ("elw_wordinstB_m", "words_of_institution_sung"),
    ("elw_ldprayer_m", "lords_prayer_sung"),
    # Prefaces
    ("elw_hc2_pref_transfig_m", "preface_transfiguration"),
    ("elw_hc2_pref_holyweek_m", "preface_holy_week"),
    ("elw_hc2_pref_ascension_m", "preface_ascension"),
    ("elw_hc2_pref_trinity_m", "preface_holy_trinity"),
    ("elw_hc2_pref_weekdays_m", "preface_weekdays"),
    ("elw_hc2_pref_apostles_m", "preface_apostles"),
    ("elw_hc2_pref_saints_m", "preface_saints"),
    ("elw_hc2_pref_healing_m", "preface_healing"),
    ("elw_hc2_pref_funeral_m", "preface_funeral"),
    ("elw_hc2_pref_marriage_m", "preface_marriage"),
    ("elw_hc2_pref_sundays_m", "preface_sundays"),
    ("elw_hc2_pref_advent_m", "preface_advent"),
    ("elw_hc2_pref_christmas_m", "preface_christmas"),
    ("elw_hc2_pref_epiphany_m", "preface_epiphany"),
    ("elw_hc2_pref_lent_m", "preface_lent"),
    ("elw_hc2_pref_easter_m", "preface_easter"),
    ("elw_hc2_pref_pentecost_m", "preface_pentecost"),
]


def detect_extension(data: bytes) -> str:
    """Detect image format from magic bytes."""
    if data[:4] == b"\x89PNG":
        return ".png"
    if data[:2] in (b"II", b"MM"):
        return ".tif"
    return ".jpg"


def download_images(client: httpx.Client) -> None:
    """Download all missing notation images."""
    print("\n" + "=" * 70)
    print("DOWNLOADING: Missing Setting Two notation images")
    print(f"Target directory: {ASSETS_DIR}")
    print("=" * 70 + "\n")

    os.makedirs(ASSETS_DIR, exist_ok=True)
    successes = []
    failures = []

    for atom_code, save_name in IMAGES_TO_DOWNLOAD:
        url = f"{BASE}/File/GetImage?atomCode={atom_code}"
        print(f"  [{len(successes)+len(failures)+1:2d}/{len(IMAGES_TO_DOWNLOAD)}] "
              f"{atom_code} ... ", end="", flush=True)
        try:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
            if len(data) < 100:
                msg = f"Tiny response ({len(data)} bytes) — may be empty/error"
                print(f"WARN: {msg}")
                failures.append((atom_code, save_name, msg))
                continue
            ext = detect_extension(data)
            filename = f"{save_name}{ext}"
            filepath = os.path.join(ASSETS_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(data)
            print(f"OK  {len(data):>8,} bytes  {ext}  -> {filename}")
            successes.append((atom_code, filename, len(data)))
        except Exception as e:
            print(f"FAILED: {e}")
            failures.append((atom_code, save_name, str(e)))
        time.sleep(0.3)

    print(f"\n{'=' * 70}")
    print(f"DOWNLOAD RESULTS: {len(successes)} succeeded, {len(failures)} failed")
    print(f"{'=' * 70}")
    if successes:
        print("\nSuccessful downloads:")
        for code, fname, size in successes:
            print(f"  OK   {code:40s} -> {fname} ({size:,} bytes)")
    if failures:
        print("\nFailed downloads:")
        for code, name, err in failures:
            print(f"  FAIL {code:40s} ({name}): {err}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    load_dotenv(env_path)

    username = os.getenv("SNDS_USERNAME")
    password = os.getenv("SNDS_PASSWORD")
    if not username or not password:
        print("ERROR: SNDS_USERNAME / SNDS_PASSWORD not set in .env")
        sys.exit(1)

    client = create_client()
    try:
        login(client, username, password)
        explore_holy_communion(client)
        download_images(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
