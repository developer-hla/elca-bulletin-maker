"""
Sundays & Seasons client — handles auth and content fetching.

All interaction with sundaysandseasons.com goes through this module.
"""

from __future__ import annotations

import io
import os
import re
import time
import zipfile
import logging

import httpx

from bulletin_maker.exceptions import (
    AuthError,
    BulletinError,
    ContentNotFoundError,
    NetworkError,
    ParseError,
)
from bulletin_maker.sns.models import DayContent, HymnLyrics, HymnResult, Reading

logger = logging.getLogger(__name__)

BASE = "https://members.sundaysandseasons.com"


class SundaysClient:
    """HTTP client for Sundays & Seasons."""

    def __init__(self, timeout: float = 30.0):
        self.client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
            },
        )
        self._logged_in = False

    # -- HTTP helpers -------------------------------------------------------

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Execute an HTTP request with one retry for transient failures."""
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                logger.debug("%s %s (attempt %d)", method, url, attempt + 1)
                resp = self.client.request(method, url, **kwargs)
                logger.debug("Response: %d (%d bytes)", resp.status_code, len(resp.content))
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (401, 403):
                    self._logged_in = False
                    raise AuthError(
                        f"Authentication failed (HTTP {status}). "
                        "Session may have expired."
                    ) from exc
                if status >= 500 and attempt == 0:
                    last_exc = exc
                    time.sleep(2)
                    continue
                raise BulletinError(
                    f"S&S returned HTTP {status} for {method} request"
                ) from exc
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    last_exc = exc
                    time.sleep(2)
                    continue
                raise NetworkError(
                    "Request timed out connecting to S&S"
                ) from exc
            except httpx.RequestError as exc:
                if attempt == 0:
                    last_exc = exc
                    time.sleep(2)
                    continue
                raise NetworkError(
                    f"Network error connecting to S&S: {exc}"
                ) from exc
        # Should not reach here, but satisfy type checker
        raise NetworkError("Request failed after retry") from last_exc

    # -- Auth ---------------------------------------------------------------

    def login(self, username: str | None = None, password: str | None = None):
        """Log in and establish a session cookie."""
        from dotenv import load_dotenv

        load_dotenv()
        username = username or os.getenv("SNDS_USERNAME")
        password = password or os.getenv("SNDS_PASSWORD")
        if not username or not password:
            raise AuthError("Credentials not provided and not found in .env")

        # Step 1: GET the login page to grab the CSRF token
        resp = self._request("GET", f"{BASE}/Account/Login")

        token_match = re.search(
            r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', resp.text
        )
        if not token_match:
            raise AuthError("Could not find CSRF token on login page")

        token = token_match.group(1)

        # Step 2: POST credentials
        resp = self._request(
            "POST",
            f"{BASE}/Account/Login",
            data={
                "__RequestVerificationToken": token,
                "UserName": username,
                "Password": password,
            },
        )

        # Check for successful login — the page should welcome the user
        if "Welcome back" in resp.text or "/Account/LogOff" in resp.text:
            self._logged_in = True
            logger.info("Logged in successfully.")
        elif "Account/Login" in str(resp.url):
            raise AuthError("Login failed — still on the login page. Check credentials.")
        else:
            # Might have redirected to home — check for nav
            if "/Planner" in resp.text:
                self._logged_in = True
                logger.info("Logged in successfully.")
            else:
                raise AuthError("Unexpected response after login")

    def _ensure_logged_in(self):
        if not self._logged_in:
            self.login()

    # -- Day Texts ----------------------------------------------------------

    def get_day_texts(self, date: str, event_date_id: int = 0) -> DayContent:
        """
        Fetch liturgical content for a date.

        Args:
            date: Date string like "2026-2-22" (no zero-padding).
            event_date_id: Internal S&S day ID. Use 0 for auto-resolve.
        """
        if not re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', date):
            raise ValueError(f"Invalid date format: {date!r}. Expected 'YYYY-M-D'.")

        self._ensure_logged_in()

        url = f"{BASE}/Home/DayTexts/{date}/{event_date_id}"
        resp = self._request("GET", url)

        day = self._parse_day_texts(date, resp.text)
        logger.debug("Parsed DayTexts: %s (%d readings)", day.title, len(day.readings))
        return day

    def _parse_day_texts(self, date: str, html: str) -> DayContent:
        """Parse the DayTexts HTML into structured content."""

        # Extract the rightpanel content
        right_match = re.search(
            r'<div[^>]*id="rightcolumn"[^>]*>(.*)',
            html,
            re.DOTALL,
        )
        if not right_match:
            raise ParseError("Could not find rightcolumn in DayTexts response")

        content = right_match.group(1)

        # Day title from <h2>
        title = ""
        h2_match = re.search(r'<h2>(.*?)</h2>', content, re.DOTALL)
        if h2_match:
            title = re.sub(r'<[^>]+>', ' ', h2_match.group(1)).strip()
            title = re.sub(r'\s+', ' ', title)

        # Extract section content between consecutive h3 tags
        def section_between_h3(heading: str) -> str:
            pattern = rf'<h3>\s*{re.escape(heading)}\s*</h3>\s*(.*?)(?=<h3>|<div class="content-download|$)'
            m = re.search(pattern, content, re.DOTALL)
            return m.group(1).strip() if m else ""

        introduction = section_between_h3("Introduction")
        confession = section_between_h3("Confession and Forgiveness")
        prayer = section_between_h3("Prayer of the Day")
        acclamation = section_between_h3("Gospel Acclamation")
        prayers = section_between_h3("Prayers of Intercession")
        offering_prayer = section_between_h3("Offering Prayer")
        invitation = section_between_h3("Invitation to Communion")
        prayer_after = section_between_h3("Prayer after Communion")
        blessing = section_between_h3("Blessing")
        dismissal = section_between_h3("Dismissal")

        # Parse readings (exclude "Gospel Acclamation" — it's a separate section)
        readings = []
        reading_pattern = re.compile(
            r'<h3>((?:First Reading|Second Reading|Psalm|Gospel(?!\s+Acclamation))(?::?\s*[^<]*))</h3>'
            r'\s*(?:<div class="reading_intro">(.*?)</div>)?'
            r'\s*<div>(.*?)</div>\s*(?=<h3>|<div class="content-download|$)',
            re.DOTALL,
        )
        for m in reading_pattern.finditer(content):
            full_label = m.group(1).strip()
            # Split label and citation
            if ":" in full_label:
                label, citation = full_label.split(":", 1)
                label = label.strip()
                citation = citation.strip()
            else:
                label = full_label
                citation = ""
            intro = m.group(2).strip() if m.group(2) else ""
            text_html = m.group(3).strip()
            readings.append(Reading(
                label=label,
                citation=citation,
                intro=intro,
                text_html=text_html,
            ))

        return DayContent(
            date=date,
            title=title,
            introduction=introduction,
            confession_html=confession,
            prayer_of_the_day_html=prayer,
            gospel_acclamation=acclamation,
            readings=readings,
            prayers_html=prayers,
            offering_prayer_html=offering_prayer,
            invitation_to_communion=invitation,
            prayer_after_communion_html=prayer_after,
            blessing_html=blessing,
            dismissal_html=dismissal,
            raw_html=content,
        )

    # -- Music Search -------------------------------------------------------

    def _get_music_form_fields(self) -> dict:
        """GET /Music and extract all search form fields."""
        resp = self._request("GET", f"{BASE}/Music")

        form_match = re.search(
            r'<form action="/Music/Search" method="post">(.*?)</form>',
            resp.text,
            re.DOTALL,
        )
        if not form_match:
            raise ParseError("Could not find music search form on /Music")

        form_html = form_match.group(1)
        fields = {}

        for m in re.finditer(r'<input[^>]+>', form_html):
            tag = m.group(0)
            name = re.search(r'name="([^"]*)"', tag)
            val = re.search(r'value="([^"]*)"', tag)
            if name:
                if 'type="checkbox"' in tag:
                    fields[name.group(1)] = "true" if "checked" in tag else "false"
                else:
                    fields[name.group(1)] = val.group(1) if val else ""

        for m in re.finditer(
            r'<select[^>]+name="([^"]*)"[^>]*>(.*?)</select>',
            form_html,
            re.DOTALL,
        ):
            selected = re.search(r'<option[^>]+selected[^>]+value="([^"]*)"', m.group(2))
            fields[m.group(1)] = selected.group(1) if selected else ""

        return fields

    def search_hymn(self, number: str, collection: str = "ELW") -> list[HymnResult]:
        """
        Search for a hymn by number in a given collection.

        Returns list of matching HymnResult (usually 1 for exact number match).
        """
        if not number or not number.strip():
            raise ValueError("Hymn number must not be empty.")
        if collection not in ("ELW", "ACS"):
            raise ValueError(f"Unknown collection: {collection!r}. Expected 'ELW' or 'ACS'.")

        self._ensure_logged_in()

        fields = self._get_music_form_fields()

        # Activate the requested collection
        collection_key_map = {
            "ELW": "Search.Categories[0].SongBooks[0].Active",
            "ACS": "Search.Categories[0].SongBooks[1].Active",
        }
        key = collection_key_map.get(collection)
        if key and key in fields:
            fields[key] = "true"

        fields["Search.HymnSongNumber"] = number

        resp = self._request("POST", f"{BASE}/Music/Search", data=fields)

        results = self._parse_search_results(resp.text)
        logger.debug("Hymn search %s %s: %d results", collection, number, len(results))
        return results

    def _parse_search_results(self, html: str) -> list[HymnResult]:
        """Parse music search result rows into HymnResult objects."""
        results = []

        # Each result is in a <tr> with a <td class="music_title" data-atom-id="...">
        row_pattern = re.compile(
            r'<tr[^>]*>\s*'
            r'<td[^>]*>(.*?)</td>\s*'           # hymn numbers cell
            r'<td[^>]*data-title="([^"]*)"[^>]*data-atom-id="(\d+)"[^>]*>'
            r'(.*?)</td>',                       # title + download links cell
            re.DOTALL,
        )

        for m in row_pattern.finditer(html):
            numbers_html = m.group(1)
            title = m.group(2)
            atom_id = m.group(3)
            links_html = m.group(4)

            # Parse hymn numbers (e.g., "ELW 504<br/>TFF 133<br/>LBW 229")
            numbers = re.sub(r'<[^>]+>', ', ', numbers_html).strip().strip(',')
            numbers = re.sub(r'\s*,\s*', ', ', numbers).strip()

            # Parse download atomIds
            harmony_id = ""
            melody_id = ""
            words_id = ""
            for link in re.finditer(
                r'data-atom-id="(\d+)"[^>]*title="[^"]*">(\w+)',
                links_html,
            ):
                link_type = link.group(2).lower()
                if link_type == "harmony":
                    harmony_id = link.group(1)
                elif link_type == "melody":
                    melody_id = link.group(1)
                elif link_type == "words":
                    words_id = link.group(1)

            results.append(HymnResult(
                atom_id=atom_id,
                title=title,
                hymn_numbers=numbers,
                harmony_atom_id=harmony_id,
                melody_atom_id=melody_id,
                words_atom_id=words_id,
            ))

        return results

    def get_hymn_details(self, atom_id: str) -> HymnResult:
        """Fetch detail for a hymn by its atomId — gets image URLs and copyright."""
        if not atom_id:
            raise ValueError("atom_id must not be empty.")

        self._ensure_logged_in()

        resp = self._request(
            "POST",
            f"{BASE}/Music/_Details",
            data={"atomId": atom_id},
        )

        html = resp.text
        result = HymnResult(atom_id=atom_id, title="")

        # Extract image URLs
        for img_match in re.finditer(r'src="(/File/GetImage\?atomCode=[^"]+)"', html):
            url = img_match.group(1).replace("&amp;", "&")
            if "_h&" in url or url.endswith("_h"):
                result.harmony_image_url = f"{BASE}{url}"
            elif "_m&" in url or url.endswith("_m"):
                result.melody_image_url = f"{BASE}{url}"

        # Extract atomCode from the image URLs
        code_match = re.search(r'atomCode=(STANZA_\d+)', html)
        if code_match:
            result.atom_code = code_match.group(1)

        # Extract copyright section
        copyright_match = re.search(
            r'id="dialog-copyrights-list">(.*?)</div>\s*</div>',
            html,
            re.DOTALL,
        )
        if copyright_match:
            result.copyright_html = copyright_match.group(1).strip()

        return result

    # -- Image Download -----------------------------------------------------

    def download_image(self, url: str) -> bytes:
        """Download an image (notation, thumbnail, etc.) and return raw bytes."""
        if not url:
            raise ValueError("Image URL must not be empty.")

        self._ensure_logged_in()

        if url.startswith("/"):
            url = f"{BASE}{url}"

        resp = self._request("GET", url)
        logger.debug("Downloaded image: %d bytes", len(resp.content))
        return resp.content

    # -- Words Download -----------------------------------------------------

    def download_words(self, atom_id: str, use_date: str) -> str:
        """Download hymn words RTF via POST /File/Download.

        Args:
            atom_id: The words_atom_id from a HymnResult.
            use_date: Date in M/D/YYYY format (e.g. "2/22/2026").

        Returns:
            Raw RTF string extracted from the ZIP response.
        """
        if not atom_id:
            raise ValueError("atom_id must not be empty.")
        if not re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', use_date):
            raise ValueError(f"Invalid use_date format: {use_date!r}. Expected 'M/D/YYYY'.")

        self._ensure_logged_in()

        resp = self._request(
            "POST",
            f"{BASE}/File/Download",
            data={
                "atomId": atom_id,
                "useType": "Worship",
                "useDate": use_date,
                "numCopies": "1",
            },
        )

        try:
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
        except zipfile.BadZipFile:
            preview = resp.content[:200].decode("utf-8", errors="replace")
            raise ParseError(
                f"S&S returned non-ZIP response for atomId={atom_id}. "
                f"Session may have expired. Response preview: {preview}"
            )
        for name in zf.namelist():
            if name.endswith(".rtf") and "PermissionsForm" not in name:
                return zf.read(name).decode("utf-8", errors="replace")

        raise ContentNotFoundError(
            f"No RTF file found in ZIP for atomId={atom_id}. "
            f"ZIP contents: {zf.namelist()}"
        )

    def fetch_hymn_lyrics(
        self, number: str, use_date: str, collection: str = "ELW"
    ) -> HymnLyrics:
        """Search for a hymn and download its lyrics as HymnLyrics.

        Args:
            number: Hymn number (e.g. "335").
            use_date: Date in M/D/YYYY format for the download license.
            collection: Hymnal collection (default "ELW").

        Returns:
            HymnLyrics populated from the S&S RTF download.
        """
        if not number or not number.strip():
            raise ValueError("Hymn number must not be empty.")
        if not re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', use_date):
            raise ValueError(f"Invalid use_date format: {use_date!r}. Expected 'M/D/YYYY'.")

        from bulletin_maker.sns.rtf_parser import parse_rtf_lyrics

        results = self.search_hymn(number, collection)
        if not results:
            raise ContentNotFoundError(f"No results for {collection} {number}")

        hymn = results[0]
        if not hymn.words_atom_id:
            raise ContentNotFoundError(
                f"No words download available for {hymn.title} ({collection} {number})"
            )

        rtf = self.download_words(hymn.words_atom_id, use_date)
        return parse_rtf_lyrics(rtf, hymn_number=number, collection=collection)

    # -- Cleanup ------------------------------------------------------------

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
