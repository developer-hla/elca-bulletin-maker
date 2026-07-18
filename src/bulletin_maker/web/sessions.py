"""In-memory per-user sessions.

Each session owns its own SundaysClient (per-instance cookie jar), the
fetched DayContent, and the hymn-lyrics cache — the same state the
desktop bridge kept on BulletinAPI. Credentials are never stored; the
S&S session cookie lives only inside the client instance.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.models import DayContent

SESSION_COOKIE = "bulletin_session"
SESSION_TTL_SECONDS = 8 * 60 * 60  # a working day


@dataclass
class Session:
    id: str
    client: Optional[SundaysClient] = None
    day: Optional[DayContent] = None
    date_str: Optional[str] = None          # "YYYY-MM-DD" from last fetch
    hymn_cache: dict = field(default_factory=dict)
    jobs: dict = field(default_factory=dict)  # job_id -> job state dict
    last_seen: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    def get_client(self) -> SundaysClient:
        if self.client is None:
            self.client = SundaysClient()
        return self.client

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None


class SessionStore:
    """Thread-safe session registry with TTL expiry."""

    def __init__(self, ttl_seconds: float = SESSION_TTL_SECONDS) -> None:
        self._sessions: dict = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def create(self) -> Session:
        session = Session(id=secrets.token_urlsafe(32))
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, session_id: Optional[str]) -> Optional[Session]:
        if not session_id:
            return None
        self._expire()
        with self._lock:
            session = self._sessions.get(session_id)
        if session is not None:
            session.touch()
        return session

    def get_or_create(self, session_id: Optional[str]) -> Session:
        session = self.get(session_id)
        return session if session is not None else self.create()

    def drop(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            session.close()

    def _expire(self) -> None:
        cutoff = time.monotonic() - self._ttl
        with self._lock:
            expired = [
                sid for sid, s in self._sessions.items() if s.last_seen < cutoff
            ]
            sessions = [self._sessions.pop(sid) for sid in expired]
        for session in sessions:
            session.close()
