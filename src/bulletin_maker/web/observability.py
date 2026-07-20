"""Structured request logging, request-scoped context, and error reporting.

Every HTTP request is tagged with a short request id, held in a contextvar
and echoed back as ``X-Request-Id``. A logging filter stamps each record with
that id plus the church/user (bound in ``session_dep``) and, inside the
generation worker, the job id and church. Two output formats are selected by
``BULLETIN_LOG_JSON``: unset/``0`` keeps a human-readable line; ``1`` emits one
JSON object per line for log aggregation.

Sentry is dormant unless ``$SENTRY_DSN`` is set; the SDK is imported lazily so
the base install never needs it.
"""

from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from starlette.datastructures import MutableHeaders

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-Id"
REQUEST_ID_LENGTH = 12
CONTEXT_FIELDS = ("request_id", "church_id", "user_id", "job_id")

# One mutable dict per request/worker, held in a single contextvar. Storing a
# shared mutable object (rather than a value per field) lets identifiers bound
# in a sync dependency reach the sync endpoint: FastAPI runs each in its own
# threadpool thread with a *copied* context, but the copies all point at the
# same dict, so in-place mutation is visible everywhere in the request.
_context: ContextVar[Optional[dict]] = ContextVar(
    "bulletin_context", default=None)

_HANDLER_FLAG = "_bulletin_observability"


# ── Request-scoped context ───────────────────────────────────────────

def _state() -> dict:
    state = _context.get()
    if state is None:
        state = {}
        _context.set(state)
    return state


def new_context(request_id: Optional[str] = None) -> None:
    """Start a fresh context (a new backing dict) for a request or worker."""
    _context.set({"request_id": request_id} if request_id else {})


def bind_context(*, request_id: Optional[str] = None,
                 church_id: Optional[int] = None,
                 user_id: Optional[int] = None,
                 job_id: Optional[str] = None) -> None:
    """Attach identifiers to the current context; ``None`` values are left
    untouched so a partial bind never clears an existing value."""
    state = _state()
    if request_id is not None:
        state["request_id"] = request_id
    if church_id is not None:
        state["church_id"] = church_id
    if user_id is not None:
        state["user_id"] = user_id
    if job_id is not None:
        state["job_id"] = job_id


def current_context() -> dict:
    state = _context.get() or {}
    return {field: state.get(field) for field in CONTEXT_FIELDS}


class RequestContextMiddleware:
    """Pure-ASGI middleware: assigns a request id, seeds a fresh context, and
    echoes the id back as a response header. Being pure ASGI (not
    ``BaseHTTPMiddleware``) it shares the request task's context, so ids bound
    downstream in dependencies reach the log records emitted by the endpoint."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex[:REQUEST_ID_LENGTH]
        new_context(request_id)

        async def send_with_request_id(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception("Unhandled error handling %s %s",
                             scope.get("method"), scope.get("path"))
            raise


# ── Logging ──────────────────────────────────────────────────────────

class ContextFilter(logging.Filter):
    """Stamps every record with the current request-scoped identifiers."""

    def filter(self, record: logging.LogRecord) -> bool:
        state = _context.get() or {}
        for field in CONTEXT_FIELDS:
            setattr(record, field, state.get(field))
        return True


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line; null context fields are omitted."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(
            record.created, tz=timezone.utc).isoformat()
        payload = {
            "ts": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _json_mode() -> bool:
    return os.environ.get("BULLETIN_LOG_JSON", "0") == "1"


def _build_formatter() -> logging.Formatter:
    if _json_mode():
        return JsonLogFormatter()
    return logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s")


def setup_logging() -> None:
    """Install our formatter + context filter on the root logger, keeping it at
    warning level. Idempotent, and it leaves uvicorn's own loggers alone (they
    carry their own handlers and do not route through ours)."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_FLAG, False):
            root.removeHandler(handler)

    handler = logging.StreamHandler()
    setattr(handler, _HANDLER_FLAG, True)
    handler.addFilter(ContextFilter())
    handler.setFormatter(_build_formatter())
    root.addHandler(handler)

    if root.level == logging.NOTSET or root.level > logging.WARNING:
        root.setLevel(logging.WARNING)


# ── Sentry (dormant by default) ──────────────────────────────────────

def init_sentry() -> None:
    """Initialize Sentry only when ``$SENTRY_DSN`` is set. Errors only —
    tracing is disabled. Imports the SDK lazily so the base install can skip
    the dependency entirely."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    from bulletin_maker.version import __version__

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("BULLETIN_ENV", "dev"),
        release=__version__,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.0,
    )
