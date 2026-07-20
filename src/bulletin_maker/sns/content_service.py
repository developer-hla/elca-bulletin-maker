"""Cached content access for Sundays & Seasons.

The single interface the web layer uses to read liturgical content. It sits
in front of the raw :class:`SundaysClient` transport: every read first
consults the ``sns_cache`` table and only falls through to a live S&S fetch
on a miss (or when ``force_refresh`` is set). Liturgical content for a given
date is stable, so cached payloads are honored for ``ttl_seconds`` (7 days by
default, set on the table).

Entitlement: cached S&S content is served only to churches with a validated
S&S link of their own. The cache is keyed by date/citation/hymn — it is shared
across churches — so an un-linked church must never be able to read it. Callers
pass ``entitled`` and the service refuses everything when it is false.

Binary assets (hymn notation images) are out of scope here and continue to be
fetched live; the ``object_key`` column on ``sns_cache`` is the future hook for
storing them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from psycopg.types.json import Jsonb

import re

from bulletin_maker.exceptions import BulletinError
from bulletin_maker.renderer.text_utils import clean_sns_html
from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.models import DayContent, HymnLyrics, HymnResult
from bulletin_maker.web import db

logger = logging.getLogger(__name__)

DAY_KEY = "day"
PASSAGE_KEY = "passage"
HYMN_KEY = "hymn"
LIBRARY_KEY = "library"

# S&S returns this plain body (HTTP 200, no ``.body`` div) for an unknown
# atom-code — it must be treated as absent, never as content.
ATOM_NOT_FOUND_MARKER = "Atom not found with code:"


def _clean_library_html(html: str) -> str:
    """Clean a /File/Preview body to newline-delimited text.

    The preview wraps each liturgical line in its own ``<div>`` (indentation
    via ``text-indent``). Converting those div boundaries to newlines lets the
    shared :func:`clean_sns_html` strip tags/entities while preserving the
    line/stanza structure, exactly as day-content texts are handled.
    """
    line_delimited = re.sub(r"</div>", "\n", html)
    return clean_sns_html(line_delimited)


class SubscriptionRequiredError(BulletinError):
    """Church has no validated S&S link; cached content must not be served."""


def cache_get(cache_key: str) -> Optional[dict]:
    """Return a fresh cached payload for ``cache_key``, or None on miss/expiry."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT payload_jsonb, fetched_at, ttl_seconds"
            " FROM sns_cache WHERE cache_key = %s",
            (cache_key,),
        ).fetchone()
    if row is None or row["payload_jsonb"] is None:
        return None
    age = (datetime.now(timezone.utc) - row["fetched_at"]).total_seconds()
    if age > row["ttl_seconds"]:
        return None
    return row["payload_jsonb"]


def cache_put(cache_key: str, payload: dict) -> None:
    """Store ``payload`` for ``cache_key``, resetting ``fetched_at`` to now."""
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sns_cache (cache_key, payload_jsonb, fetched_at)"
            " VALUES (%s, %s, now())"
            " ON CONFLICT (cache_key) DO UPDATE SET"
            " payload_jsonb = EXCLUDED.payload_jsonb, fetched_at = now()",
            (cache_key, Jsonb(payload)),
        )


class ContentService:
    """Cached, entitlement-gated access to S&S content.

    ``client_provider`` is called lazily (only on a cache miss / refresh) so a
    served cache hit never establishes an S&S session.
    """

    def __init__(
        self,
        entitled: bool,
        client_provider: Callable[[], SundaysClient],
    ) -> None:
        self._entitled = entitled
        self._client_provider = client_provider

    def _require_entitlement(self) -> None:
        if not self._entitled:
            raise SubscriptionRequiredError(
                "No validated Sundays & Seasons link — cached content is not "
                "available without a subscription of your own."
            )

    def get_day_content(
        self, api_date: str, force_refresh: bool = False
    ) -> DayContent:
        self._require_entitlement()
        cache_key = f"{DAY_KEY}:{api_date}"
        cached = None if force_refresh else cache_get(cache_key)
        if cached is not None:
            return DayContent.from_dict(cached)
        day = self._client_provider().get_day_texts(api_date)
        cache_put(cache_key, day.to_dict())
        return day

    def get_passage(self, citation: str, force_refresh: bool = False) -> str:
        self._require_entitlement()
        cache_key = f"{PASSAGE_KEY}:{citation.strip()}"
        cached = None if force_refresh else cache_get(cache_key)
        if cached is not None:
            return cached["html"]
        html = self._client_provider().search_passage(citation)
        cache_put(cache_key, {"html": html})
        return html

    def get_hymn_lyrics(
        self,
        collection: str,
        number: str,
        use_date: str,
        force_refresh: bool = False,
    ) -> HymnLyrics:
        self._require_entitlement()
        cache_key = f"{HYMN_KEY}:{collection}:{number}"
        cached = None if force_refresh else cache_get(cache_key)
        if cached is not None:
            return HymnLyrics.from_dict(cached)
        lyrics = self._client_provider().fetch_hymn_lyrics(
            number, use_date, collection)
        cache_put(cache_key, lyrics.to_dict())
        return lyrics

    def search_hymn(self, number: str, collection: str) -> list[HymnResult]:
        self._require_entitlement()
        return self._client_provider().search_hymn(number, collection)

    def get_library_item(
        self, atom_code: str, force_refresh: bool = False
    ) -> Optional[str]:
        """Fetch a Library item's text by atom-code (cached, entitlement-gated).

        Pulls ``/File/Preview?atomCode=`` once per church per item — the
        ordinary/occasion text is stable, so the cached value is reused. Returns
        None when S&S reports the atom-code is unknown; the caller falls back.
        """
        self._require_entitlement()
        cache_key = f"{LIBRARY_KEY}:{atom_code}"
        cached = None if force_refresh else cache_get(cache_key)
        if cached is not None:
            return cached["text"]
        html = self._client_provider().fetch_preview(atom_code)
        if ATOM_NOT_FOUND_MARKER in html:
            return None
        text = _clean_library_html(html)
        cache_put(cache_key, {"text": text})
        return text
