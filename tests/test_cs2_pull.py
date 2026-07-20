"""Pull-live liturgical text from the S&S Library (CS-2).

Verifies the ``/File/Preview`` fetch (cleaned, cached, not-found -> None), and
that the content-source layer pulls a mapped gap-fill key ONLY when entitled
with an injected ``sns_fetch`` — the offline / parity path (``sns_fetch=None``)
and an unentitled church never pull, and a church override always wins.  No
live S&S calls: the client is mocked throughout.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from bulletin_maker.core.content_source import (
    ENTITLEMENT_PLACEHOLDER,
    PULL_ATOM_CODES,
    ContentContext,
    resolve_text,
)
from bulletin_maker.sns.content_service import ContentService, cache_get
from bulletin_maker.web import db

TEST_DATABASE_URL = os.environ.get(
    "BULLETIN_TEST_DATABASE_URL", "postgresql://localhost/bulletin_maker_test")

_TRUNCATE = (
    "TRUNCATE churches, users, past_runs, sessions, auth_tokens, jobs,"
    " artifacts, sns_cache, audit_log RESTART IDENTITY CASCADE"
)

PULL_KEY = "library.apostles_creed"
PULL_ATOM = PULL_ATOM_CODES[PULL_KEY]

PREVIEW_BODY_HTML = (
    '<div class="body"><p>'
    '<div style="text-indent: 0em"><strong>I believe in God, the Father'
    ' almighty,</strong></div>'
    '<div style="text-indent: 1em"><strong>creator of heaven and'
    ' earth.</strong></div>'
    '</p></div>'
)
EXPECTED_TEXT = (
    "I believe in God, the Father almighty,\n"
    "creator of heaven and earth."
)
NOT_FOUND_BODY = f"Atom not found with code: {PULL_ATOM}"


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    db.reset_for_tests()
    with db.connect() as conn:
        conn.execute(_TRUNCATE)


def _service(client, entitled=True):
    return ContentService(entitled=entitled, client_provider=lambda: client)


class TestGetLibraryItem:

    def test_returns_cleaned_line_structured_text(self):
        client = MagicMock()
        client.fetch_preview.return_value = PREVIEW_BODY_HTML
        service = _service(client)

        assert service.get_library_item(PULL_ATOM) == EXPECTED_TEXT
        client.fetch_preview.assert_called_once_with(PULL_ATOM)

    def test_atom_not_found_returns_none(self):
        client = MagicMock()
        client.fetch_preview.return_value = NOT_FOUND_BODY
        service = _service(client)

        assert service.get_library_item(PULL_ATOM) is None

    def test_caches_and_second_call_does_not_refetch(self):
        client = MagicMock()
        client.fetch_preview.return_value = PREVIEW_BODY_HTML
        service = _service(client)

        first = service.get_library_item(PULL_ATOM)
        second = service.get_library_item(PULL_ATOM)

        assert first == second == EXPECTED_TEXT
        client.fetch_preview.assert_called_once()
        assert cache_get(f"library:{PULL_ATOM}") == {"text": EXPECTED_TEXT}

    def test_cache_shared_across_services(self):
        client = MagicMock()
        client.fetch_preview.return_value = PREVIEW_BODY_HTML
        _service(client).get_library_item(PULL_ATOM)

        client2 = MagicMock()
        assert _service(client2).get_library_item(PULL_ATOM) == EXPECTED_TEXT
        client2.fetch_preview.assert_not_called()


class TestResolveTextPull:

    def test_entitled_with_fetch_returns_pulled_text(self):
        fetch = MagicMock(return_value=EXPECTED_TEXT)
        ctx = ContentContext(entitled=True, sns_fetch=fetch)

        assert resolve_text(PULL_KEY, ctx) == EXPECTED_TEXT
        fetch.assert_called_once_with(PULL_ATOM)

    def test_offline_no_fetch_falls_through_to_placeholder(self):
        ctx = ContentContext(entitled=True, sns_fetch=None)
        assert resolve_text(PULL_KEY, ctx) == ENTITLEMENT_PLACEHOLDER

    def test_pull_returning_none_falls_through_to_placeholder(self):
        fetch = MagicMock(return_value=None)
        ctx = ContentContext(entitled=True, sns_fetch=fetch)
        assert resolve_text(PULL_KEY, ctx) == ENTITLEMENT_PLACEHOLDER

    def test_church_override_wins_over_pull(self):
        override = "OUR CONGREGATION'S OWN CREED"
        fetch = MagicMock(return_value=EXPECTED_TEXT)
        ctx = ContentContext(
            entitled=True, sns_fetch=fetch, church_texts={PULL_KEY: override})

        assert resolve_text(PULL_KEY, ctx) == override
        fetch.assert_not_called()

    def test_unentitled_never_pulls(self):
        fetch = MagicMock(return_value=EXPECTED_TEXT)
        ctx = ContentContext(entitled=False, sns_fetch=fetch)

        assert resolve_text(PULL_KEY, ctx) == ENTITLEMENT_PLACEHOLDER
        fetch.assert_not_called()

    def test_no_sunday_ordinary_key_is_pull_mapped(self):
        """Guardrail: never map a bundled Sunday-ordinary key to an atom-code."""
        for key in PULL_ATOM_CODES:
            assert not key.startswith("elw.")
            assert not key.startswith("house.")
