"""Durable, DB-backed app sessions with process-memory runtime state.

The session token lives in a cookie; only its sha256 hash is stored in the
`sessions` table, with a sliding 30-day expiry. Identity (user + church) is
read from the database, so sessions survive restarts. Runtime state that
cannot be serialized lives in process memory: the Sundays & Seasons client
is cached per church (shared across that church's sessions); the fetched
day and hymn-lyrics cache are cached per session.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.models import DayContent
from bulletin_maker.web import db

SESSION_COOKIE = "bulletin_session"
SESSION_TTL = timedelta(days=30)
SESSION_TTL_SECONDS = int(SESSION_TTL.total_seconds())
REFRESH_AFTER = timedelta(hours=1)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── sessions table persistence ───────────────────────────────────────

def open_session(token_hash: str, user_id: int) -> None:
    """Persist a new session and opportunistically prune expired ones."""
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at)"
            " VALUES (%s, %s, %s)",
            (token_hash, user_id, _now() + SESSION_TTL))
        conn.execute("DELETE FROM sessions WHERE expires_at <= now()")


def lookup_session(token_hash: str) -> Optional[dict]:
    with db.connect() as conn:
        return conn.execute(
            "SELECT s.user_id AS user_id, u.church_id AS church_id,"
            " s.last_seen AS last_seen FROM sessions s"
            " JOIN users u ON u.id = s.user_id"
            " WHERE s.token_hash = %s AND s.expires_at > now()",
            (token_hash,)).fetchone()


def refresh_session(token_hash: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE sessions SET last_seen = now(), expires_at = %s"
            " WHERE token_hash = %s",
            (_now() + SESSION_TTL, token_hash))


def delete_session(token_hash: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))


def delete_user_sessions(user_id: int) -> list:
    with db.connect() as conn:
        rows = conn.execute(
            "DELETE FROM sessions WHERE user_id = %s RETURNING token_hash",
            (user_id,)).fetchall()
    return [row["token_hash"] for row in rows]


# ── Per-session runtime state ────────────────────────────────────────

@dataclass
class RuntimeState:
    """Process-memory state for one session — never persisted."""

    day: Optional[DayContent] = None
    date_str: Optional[str] = None
    hymn_cache: dict = field(default_factory=dict)

    def clear(self) -> None:
        self.day = None
        self.date_str = None
        self.hymn_cache.clear()


class Session:
    """Per-request facade over a durable session row and its runtime state.

    Identity fields come from the database; runtime attributes are proxied
    to the store's process-memory caches. An anonymous visitor gets a
    facade with an empty token and no identity.
    """

    def __init__(self, store: "SessionStore", token: str,
                 user_id: Optional[int], church_id: Optional[int]) -> None:
        self._store = store
        self.token = token
        self.token_hash = hash_token(token) if token else ""
        self.user_id = user_id
        self.church_id = church_id

    @property
    def id(self) -> str:
        return self.token

    @property
    def _runtime(self) -> RuntimeState:
        return self._store.runtime_for(self.token_hash)

    @property
    def day(self) -> Optional[DayContent]:
        return self._runtime.day

    @day.setter
    def day(self, value: Optional[DayContent]) -> None:
        self._runtime.day = value

    @property
    def date_str(self) -> Optional[str]:
        return self._runtime.date_str

    @date_str.setter
    def date_str(self, value: Optional[str]) -> None:
        self._runtime.date_str = value

    @property
    def hymn_cache(self) -> dict:
        return self._runtime.hymn_cache

    @property
    def client(self) -> Optional[SundaysClient]:
        return self._store.get_client(self.church_id)

    @client.setter
    def client(self, value: Optional[SundaysClient]) -> None:
        self._store.set_client(self.church_id, value)

    def sign_out(self) -> None:
        self._store.end_session(self)
        self.user_id = None
        self.church_id = None

    def close(self) -> None:
        self._store.close_client(self.church_id)


class SessionStore:
    """Resolves cookies to sessions and owns the process-memory caches."""

    def __init__(self) -> None:
        self._runtime: dict = {}
        self._clients: dict = {}
        self._lock = threading.Lock()

    def runtime_for(self, token_hash: str) -> RuntimeState:
        with self._lock:
            state = self._runtime.get(token_hash)
            if state is None:
                state = RuntimeState()
                self._runtime[token_hash] = state
            return state

    def resolve(self, token: Optional[str]) -> Session:
        if not token:
            return Session(self, "", None, None)
        token_hash = hash_token(token)
        row = lookup_session(token_hash)
        if row is None:
            return Session(self, "", None, None)
        self._maybe_refresh(token_hash, row["last_seen"])
        return Session(self, token, row["user_id"], row["church_id"])

    def _maybe_refresh(self, token_hash: str,
                       last_seen: Optional[datetime]) -> None:
        if last_seen is None or _now() - last_seen >= REFRESH_AFTER:
            refresh_session(token_hash)

    def login(self, user_id: int, church_id: int) -> str:
        token = secrets.token_urlsafe(32)
        open_session(hash_token(token), user_id)
        return token

    def end_session(self, session: Session) -> None:
        if session.token_hash:
            delete_session(session.token_hash)
        self._drop_runtime(session.token_hash)

    def invalidate_user(self, user_id: int) -> None:
        for token_hash in delete_user_sessions(user_id):
            self._drop_runtime(token_hash)

    def _drop_runtime(self, token_hash: str) -> None:
        with self._lock:
            state = self._runtime.pop(token_hash, None)
        if state is not None:
            state.clear()

    def get_client(self, church_id: Optional[int]) -> Optional[SundaysClient]:
        if church_id is None:
            return None
        with self._lock:
            return self._clients.get(church_id)

    def set_client(self, church_id: Optional[int],
                   client: Optional[SundaysClient]) -> None:
        if church_id is None:
            return
        with self._lock:
            self._clients[church_id] = client

    def close_client(self, church_id: Optional[int]) -> None:
        if church_id is None:
            return
        with self._lock:
            client = self._clients.pop(church_id, None)
        if client is not None:
            client.close()
