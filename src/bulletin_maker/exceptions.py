"""Custom exception hierarchy for bulletin_maker."""

from __future__ import annotations


class BulletinError(Exception):
    """Base exception for all bulletin_maker errors."""


class AuthError(BulletinError):
    """Authentication or credential errors with Sundays & Seasons."""


class ParseError(BulletinError):
    """Errors parsing S&S HTML, RTF, or other content formats."""


class ContentNotFoundError(BulletinError):
    """Expected content (hymn, reading, image) was not found."""


class NetworkError(BulletinError):
    """Transient network errors (timeout, connection refused, DNS failure)."""
