"""FastAPI application — the web adapter over the core layer.

Auth model: users belong to a church and sign in with an app account
(email + password). The church links its Sundays & Seasons account once
(admin only); the credential is stored encrypted and used lazily to log
into S&S when content is fetched. Volunteers never handle the S&S
password.

Registration: the first church registers freely (local first run);
after that, new churches require $BULLETIN_REGISTRATION_CODE. Members
join their church with its invite code.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from bulletin_maker.core import library as rite_library
from bulletin_maker.core.calendar import (
    calendar_provider_keys,
    get_calendar_provider,
)
from bulletin_maker.core.content_source import ContentContext
from bulletin_maker.core.content_views import (
    build_liturgical_text_options,
    build_reading_preview,
)
from bulletin_maker.core.rite import (
    Rite,
    RiteError,
    RiteValidationError,
    validate_rite,
)
from bulletin_maker.core.documents import DEFAULT_SELECTION, generate_documents
from bulletin_maker.core.naming import build_date_suffix
from bulletin_maker.core.profile import (
    PROFILE_FIELDS,
    load_profile,
    profile_from_dict,
    profile_to_dict,
)
from bulletin_maker.core.service_form import build_service_config
from bulletin_maker.exceptions import (
    AuthError,
    BulletinError,
    ContentNotFoundError,
    NetworkError,
)
from bulletin_maker.renderer.paper import PAPER_PRESETS
from bulletin_maker.renderer.season import (
    fill_seasonal_defaults,
    get_preface_options,
    get_seasonal_config,
)
from bulletin_maker.renderer.settings import SETTINGS
from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.content_service import ContentService
from bulletin_maker.sns.service_fill import SECTION_MAP, fill_section
from bulletin_maker.web import (
    artifacts,
    auth_flows,
    church_texts,
    db,
    jobstore,
    members,
    observability,
    operator,
    plans,
    rites,
    security,
)
from bulletin_maker.web.sessions import (
    SESSION_COOKIE, SESSION_TTL_SECONDS, Session, SessionStore)

logger = logging.getLogger(__name__)

RESTART_JOB_MESSAGE = (
    "The server restarted while this bulletin was generating. "
    "Please generate again."
)

SPA_DIR = Path(__file__).resolve().parents[1] / "ui" / "templates"

ALLOWED_COVER_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MAX_COVER_BYTES = 20 * 1024 * 1024
MIN_PASSWORD_LENGTH = 8

CALENDAR_PROVIDER_LABELS = {
    "sns": "Sundays & Seasons",
    "rcl": "Revised Common Lectionary (computed)",
    "manual": "Manual (sermon series / no lectionary)",
}

AUTH_LIMIT = 10
AUTH_WINDOW_SECONDS = 300


def _error_type(error: Exception) -> str:
    if isinstance(error, AuthError):
        return "auth"
    if isinstance(error, NetworkError):
        return "network"
    if isinstance(error, (ValueError, TypeError)):
        return "validation"
    return "internal"


def _fail(status: int, error: Exception) -> HTTPException:
    detail = {"error": str(error), "error_type": _error_type(error)}
    if isinstance(error, AuthError):
        detail["auth_error"] = True
    return HTTPException(status_code=status, detail=detail)


def _validation(message: str, status: int = 422) -> HTTPException:
    return HTTPException(status_code=status, detail={
        "error": message, "error_type": "validation"})


def _auth_required() -> HTTPException:
    return HTTPException(status_code=401, detail={
        "error": "Please sign in.", "error_type": "auth", "auth_error": True})


def _suspended() -> HTTPException:
    return HTTPException(status_code=401, detail={
        "error": "This account is suspended — contact support.",
        "error_type": "auth", "suspended": True})


def _guard_not_suspended(user: dict) -> None:
    """Refuse a disabled church's members; operators are always exempt."""
    if user["operator"]:
        return
    church = db.get_church(user["church_id"])
    if church is not None and church["disabled"]:
        raise _suspended()


class LoginRateLimiter:
    """Per-address sliding-window limiter for auth endpoints."""

    def __init__(self, limit: int = AUTH_LIMIT,
                 window: float = AUTH_WINDOW_SECONDS) -> None:
        self._attempts: dict = {}
        self._lock = threading.Lock()
        self._limit = limit
        self._window = window

    def check(self, address: str) -> bool:
        now = time.monotonic()
        with self._lock:
            attempts = [t for t in self._attempts.get(address, [])
                        if now - t < self._window]
            if len(attempts) >= self._limit:
                self._attempts[address] = attempts
                return False
            attempts.append(now)
            self._attempts[address] = attempts
            return True


def _import_legacy_runs(church_id: int) -> None:
    """One-time migration of pre-accounts past runs into the church."""
    legacy = Path.home() / ".bulletin-maker" / "past_runs.json"
    if not legacy.exists():
        return
    try:
        runs = json.loads(legacy.read_text())
    except (ValueError, OSError):
        return
    for run in reversed(runs if isinstance(runs, list) else []):
        db.save_past_run(church_id, run.get("form_data", {}),
                         run.get("metadata", {}))
    legacy.rename(legacy.with_suffix(".json.migrated"))
    logger.warning("Migrated %d legacy past runs", len(runs))


def _seed_profile(church_name: str) -> dict:
    """New churches start from the bundled defaults with their own name."""
    profile = profile_to_dict(load_profile())
    profile["church_name"] = church_name
    return profile


def _validate_account_fields(payload: dict) -> tuple:
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    display_name = (payload.get("display_name") or "").strip()
    if "@" not in email or len(email) < 5:
        raise _validation("Enter a valid email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise _validation(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    return email, password, display_name


def create_app() -> FastAPI:
    observability.setup_logging()
    observability.init_sentry()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        recovered = jobstore.recover_stale_jobs(RESTART_JOB_MESSAGE)
        if recovered:
            logger.warning("Failed %d job(s) left running by a restart",
                           recovered)
        yield

    app = FastAPI(title="Bulletin Maker", docs_url=None, redoc_url=None,
                  lifespan=lifespan)
    app.add_middleware(observability.RequestContextMiddleware)
    store = SessionStore()
    hosted = os.environ.get("BULLETIN_HOSTED") == "1"
    limiter = LoginRateLimiter()
    token_limiter = LoginRateLimiter()

    @app.exception_handler(plans.PlanLimitError)
    def _plan_limit(request: Request, exc: plans.PlanLimitError):
        return JSONResponse(status_code=403, content={"detail": {
            "error": str(exc), "error_type": "plan_limit"}})

    @app.exception_handler(Exception)
    def _unhandled(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": {
            "error": "Something went wrong on our end. Please try again.",
            "error_type": "internal"}})

    def session_dep(request: Request) -> Session:
        session = store.resolve(request.cookies.get(SESSION_COOKIE))
        observability.bind_context(
            church_id=session.church_id, user_id=session.user_id)
        return session

    def require_user(session: Session) -> dict:
        if session.user_id is None:
            raise _auth_required()
        user = db.get_user(session.user_id)
        if user is None:
            session.sign_out()
            raise _auth_required()
        _guard_not_suspended(user)
        return user

    def require_admin(session: Session) -> dict:
        user = require_user(session)
        if user["role"] != "admin":
            raise _validation("Only a church admin can do that.", status=403)
        return user

    def require_operator(session: Session) -> dict:
        user = require_user(session)
        if not user["operator"]:
            raise _validation("Operators only.", status=403)
        return user

    def church_of(session: Session) -> dict:
        church = db.get_church(session.church_id)
        if church is None:
            session.sign_out()
            raise _auth_required()
        return church

    def _check_rate(request: Request) -> None:
        if not hosted:
            return
        address = request.client.host if request.client else "unknown"
        if not limiter.check(address):
            raise _validation(
                "Too many attempts — wait a few minutes.", status=429)

    def _check_token_rate(request: Request, email_address: str) -> None:
        if not hosted:
            return
        address = request.client.host if request.client else "unknown"
        key = f"{email_address.strip().lower()}|{address}"
        if not token_limiter.check(key):
            raise _validation(
                "Too many requests — wait a few minutes.", status=429)

    def _sns_unlinked() -> HTTPException:
        return HTTPException(status_code=409, detail={
            "error": "No Sundays & Seasons account is linked yet. "
                     "A church admin can link one under Settings.",
            "error_type": "validation", "sns_unlinked": True,
        })

    def _build_sns_client(session: Session) -> SundaysClient:
        """The church's S&S client, logging in lazily with the linked
        credential. Assumes the church is already known to be linked."""
        if session.client is not None:
            return session.client
        church = church_of(session)
        password = security.decrypt_secret(church["sns_password_enc"])
        client = SundaysClient()
        try:
            client.login(church["sns_username"], password)
        except BulletinError:
            client.close()
            raise
        session.client = client
        return client

    def content_service(session: Session) -> ContentService:
        """Cached content interface for the church. Raises the same
        no-account-linked error the client used to, before any content read,
        so the cache can never serve S&S content without a subscription."""
        church = church_of(session)
        if not church["sns_username"] or not church["sns_password_enc"]:
            raise _sns_unlinked()
        return ContentService(
            entitled=True,
            client_provider=lambda: _build_sns_client(session),
        )

    def _sign_in(user: dict, response: Response) -> dict:
        token = store.login(user["id"], user["church_id"])
        response.set_cookie(
            SESSION_COOKIE, token, max_age=SESSION_TTL_SECONDS,
            httponly=True, samesite="lax", secure=hosted,
        )
        church = db.get_church(user["church_id"])
        return {
            "success": True,
            "user": {"email": user["email"],
                     "display_name": user["display_name"],
                     "role": user["role"]},
            "church": {"name": church["name"]},
            "sns_linked": bool(church["sns_username"]),
            "operator": bool(user["operator"]),
        }

    # ── Instance / registration ───────────────────────────────────────

    @app.get("/api/instance")
    def instance_info():
        count = db.church_count()
        code_set = bool(os.environ.get("BULLETIN_REGISTRATION_CODE"))
        return {
            "success": True,
            "has_churches": count > 0,
            "registration_open": count == 0 or code_set,
        }

    @app.post("/api/register")
    def register(payload: dict, request: Request, response: Response):
        _check_rate(request)
        church_name = (payload.get("church_name") or "").strip()
        if not church_name:
            raise _validation("Enter your church's name.")
        email, password, display_name = _validate_account_fields(payload)

        count = db.church_count()
        expected_code = os.environ.get("BULLETIN_REGISTRATION_CODE", "")
        if count > 0:
            supplied = payload.get("registration_code") or ""
            if not expected_code or not secrets.compare_digest(
                    supplied, expected_code):
                raise _validation(
                    "Registration is closed on this server. "
                    "Ask the person who runs it for a registration code.",
                    status=403)

        if db.get_user_by_email(email) is not None:
            raise _validation("That email already has an account.", status=409)

        church = db.create_church(church_name, _seed_profile(church_name))
        user = db.create_user(
            church["id"], email, security.hash_password(password),
            display_name, role="admin")
        if count == 0:
            _import_legacy_runs(church["id"])
        logger.warning("Registered church %r (admin %s)", church_name, email)
        operator.audit(user["id"], church["id"],
                       operator.ACTION_CHURCH_REGISTERED, {"name": church_name})
        auth_flows.send_verification(user)
        return _sign_in(user, response)

    @app.post("/api/join")
    def join(payload: dict, request: Request, response: Response):
        _check_rate(request)
        invite_code = (payload.get("invite_code") or "").strip()
        church = db.get_church_by_invite(invite_code) if invite_code else None
        if church is None:
            raise _validation("That invite code isn't valid.", status=403)
        plans.check_limit(church, "join")
        email, password, display_name = _validate_account_fields(payload)
        if db.get_user_by_email(email) is not None:
            raise _validation("That email already has an account.", status=409)
        user = db.create_user(
            church["id"], email, security.hash_password(password),
            display_name, role="member")
        operator.audit(user["id"], church["id"],
                       operator.ACTION_MEMBER_JOINED, {"email": email})
        auth_flows.send_verification(user)
        return _sign_in(user, response)

    # ── App sessions ──────────────────────────────────────────────────

    @app.post("/api/session")
    def login(payload: dict, request: Request, response: Response):
        _check_rate(request)
        email = (payload.get("email") or "").strip()
        password = payload.get("password") or ""
        user = db.get_user_by_email(email)
        if user is None or not security.verify_password(
                password, user["password_hash"]):
            raise HTTPException(status_code=401, detail={
                "error": "Email or password is incorrect.",
                "error_type": "auth"})
        _guard_not_suspended(user)
        return _sign_in(user, response)

    @app.get("/api/session")
    def whoami(session: Session = Depends(session_dep)):
        if session.user_id is None:
            return {"success": True, "authenticated": False}
        user = db.get_user(session.user_id)
        if user is None:
            session.sign_out()
            return {"success": True, "authenticated": False}
        _guard_not_suspended(user)
        church = db.get_church(user["church_id"])
        return {
            "success": True,
            "authenticated": True,
            "user": {"email": user["email"],
                     "display_name": user["display_name"],
                     "role": user["role"]},
            "church": {"name": church["name"]},
            "sns_linked": bool(church["sns_username"]),
            "operator": bool(user["operator"]),
        }

    @app.delete("/api/session")
    def logout(response: Response, session: Session = Depends(session_dep)):
        session.sign_out()
        response.delete_cookie(SESSION_COOKIE)
        return {"success": True}

    # ── Password reset / magic link / verification ────────────────────

    def _verify_email(token: str) -> dict:
        if not auth_flows.verify_email(token):
            raise _validation(
                "This verification link is invalid or has expired.",
                status=400)
        return {"success": True}

    @app.post("/api/auth/forgot")
    def forgot_password(payload: dict, request: Request):
        email_address = (payload.get("email") or "").strip()
        _check_token_rate(request, email_address)
        auth_flows.request_password_reset(email_address)
        return {"success": True}

    @app.post("/api/auth/reset")
    def reset_password(payload: dict):
        token = payload.get("token") or ""
        new_password = payload.get("new_password") or ""
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise _validation(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        user_id = auth_flows.reset_password(token, new_password)
        if user_id is None:
            raise _validation(
                "This reset link is invalid or has expired.", status=400)
        store.invalidate_user(user_id)
        return {"success": True}

    @app.post("/api/auth/magic")
    def magic_link(payload: dict, request: Request):
        email_address = (payload.get("email") or "").strip()
        _check_token_rate(request, email_address)
        auth_flows.request_magic_link(email_address)
        return {"success": True}

    @app.post("/api/auth/magic/consume")
    def magic_consume(payload: dict, response: Response):
        token = payload.get("token") or ""
        user_id = auth_flows.consume_magic_link(token)
        user = db.get_user(user_id) if user_id is not None else None
        if user is None:
            raise _validation(
                "This sign-in link is invalid or has expired.", status=400)
        return _sign_in(user, response)

    @app.get("/api/auth/verify")
    def verify_email_get(token: str):
        return _verify_email(token)

    @app.post("/api/auth/verify")
    def verify_email_post(payload: dict):
        return _verify_email(payload.get("token") or "")

    # ── Church settings ───────────────────────────────────────────────

    @app.get("/api/church")
    def get_church_settings(session: Session = Depends(session_dep)):
        user = require_user(session)
        church = church_of(session)
        result = {
            "success": True,
            "name": church["name"],
            "profile": json.loads(church["profile_json"]),
            "sns_linked": bool(church["sns_username"]),
            "options": {
                "liturgical_setting": [
                    {"key": s.key, "label": s.label}
                    for s in SETTINGS.values()
                ],
                "paper_size": [
                    {"key": p.key, "label": p.label}
                    for p in PAPER_PRESETS.values()
                ],
                "calendar_provider": [
                    {"key": key, "label": CALENDAR_PROVIDER_LABELS[key]}
                    for key in sorted(calendar_provider_keys())
                ],
            },
            "is_admin": user["role"] == "admin",
        }
        if user["role"] == "admin":
            result["invite_code"] = church["invite_code"]
            result["sns_username"] = church["sns_username"]
        return result

    @app.put("/api/church/profile")
    def update_profile(payload: dict, session: Session = Depends(session_dep)):
        require_admin(session)
        church = church_of(session)
        profile = json.loads(church["profile_json"])
        # Churches registered before calendar_provider existed have no such
        # key in their stored profile_json — default it in rather than
        # rejecting every future edit of an old church's profile.
        profile.setdefault("calendar_provider", "sns")
        for field in PROFILE_FIELDS:
            if field in payload:
                profile[field] = payload[field]
        if profile.get("liturgical_setting") not in SETTINGS:
            raise _validation("Choose a liturgical setting from the list.")
        if profile.get("paper_size") not in PAPER_PRESETS:
            raise _validation("Choose a paper size from the list.")
        if profile.get("calendar_provider") not in calendar_provider_keys():
            raise _validation("Choose a calendar provider from the list.")
        if not (profile.get("church_name") or "").strip():
            raise _validation("The church name cannot be empty.")
        try:
            profile_from_dict(profile)
        except (TypeError, ValueError) as e:
            raise _validation(f"Invalid profile: {e}")
        db.update_church_profile(church["id"], profile)
        return {"success": True, "profile": profile}

    @app.put("/api/church/sns-link")
    def link_sns(payload: dict, request: Request,
                 session: Session = Depends(session_dep)):
        user = require_admin(session)
        _check_rate(request)
        church = church_of(session)
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        if not username or not password:
            raise _validation("Enter the Sundays & Seasons email and password.")

        # Prove the credential works before storing it
        probe = SundaysClient()
        try:
            probe.login(username, password)
        except AuthError as e:
            raise _fail(401, e)
        except BulletinError as e:
            raise _fail(502, e)
        finally:
            probe.close()

        db.set_sns_link(church["id"], username,
                        security.encrypt_secret(password))
        session.close()  # drop any client using the old credential
        logger.warning("S&S account linked for church %r", church["name"])
        operator.audit(user["id"], church["id"], operator.ACTION_SNS_LINKED, {})
        return {"success": True, "sns_username": username}

    # ── Church members (admin) ────────────────────────────────────────

    @app.get("/api/church/members")
    def list_members(session: Session = Depends(session_dep)):
        user = require_admin(session)
        roster = members.list_members(session.church_id)
        for row in roster:
            row["is_you"] = row["id"] == user["id"]
        return {"success": True, "members": roster}

    @app.delete("/api/church/members/{user_id}")
    def remove_member(user_id: int, session: Session = Depends(session_dep)):
        admin = require_admin(session)
        target = members.get_member(session.church_id, user_id)
        if target is None:
            raise _validation("That member isn't in your church.", status=404)
        if target["role"] == "admin" and members.admin_count(
                session.church_id) <= 1:
            raise _validation("You can't remove the last admin.")
        if user_id == admin["id"]:
            raise _validation("You can't remove yourself.")
        members.delete_member(session.church_id, user_id)
        store.invalidate_user(user_id)
        logger.warning("Removed member %d from church %d",
                       user_id, session.church_id)
        return {"success": True}

    @app.post("/api/church/invite/send")
    def send_invite(payload: dict, request: Request,
                    session: Session = Depends(session_dep)):
        require_admin(session)
        to_email = (payload.get("email") or "").strip()
        if "@" not in to_email or len(to_email) < 5:
            raise _validation("Enter a valid email address.")
        _check_token_rate(request, to_email)
        church = church_of(session)
        members.send_invite(church, to_email)
        return {"success": True}

    @app.post("/api/church/invite/regenerate")
    def regenerate_invite(session: Session = Depends(session_dep)):
        require_admin(session)
        invite_code = members.regenerate_invite(session.church_id)
        return {"success": True, "invite_code": invite_code}

    @app.get("/api/church/usage")
    def church_usage(session: Session = Depends(session_dep)):
        require_admin(session)
        return {
            "success": True,
            "generates_this_month": members.generates_this_month(
                session.church_id),
            "member_count": members.member_count(session.church_id),
        }

    # ── Church text library (LWS-1) ────────────────────────────────────

    def _validate_text_payload(payload: dict) -> tuple:
        kind = payload.get("kind") or ""
        name = (payload.get("name") or "").strip()
        body = payload.get("body")
        if kind not in church_texts.ALLOWED_KINDS:
            raise _validation("Choose a valid text field.")
        if not name:
            raise _validation("Give this saved text a name.")
        if kind in church_texts.STRUCTURED_KINDS:
            if not isinstance(body, list) or not body:
                raise _validation("Add at least one line before saving.")
            for entry in body:
                if not isinstance(entry, dict) or not (entry.get("text") or "").strip():
                    raise _validation("Every line needs text.")
        elif not isinstance(body, str) or not body.strip():
            raise _validation("Enter some text before saving.")
        return kind, name, body

    @app.get("/api/church/texts")
    def list_church_texts(kind: str = None,
                          session: Session = Depends(session_dep)):
        require_user(session)
        return {"success": True,
                "texts": church_texts.list_texts(session.church_id, kind)}

    @app.post("/api/church/texts")
    def save_church_text(payload: dict, session: Session = Depends(session_dep)):
        require_admin(session)
        kind, name, body = _validate_text_payload(payload)
        saved = church_texts.save_text(session.church_id, kind, name, body)
        return {"success": True, "text": saved}

    @app.delete("/api/church/texts/{text_id}")
    def delete_church_text(text_id: int, session: Session = Depends(session_dep)):
        require_admin(session)
        if not church_texts.delete_text(session.church_id, text_id):
            raise _validation("That saved text isn't in your church.", status=404)
        return {"success": True}

    # ── Rites (LWS-1 picker) ────────────────────────────────────────────

    def _rite_summary(rite) -> dict:
        return {
            "id": rite.id, "name": rite.name,
            "occasion": rite.occasion, "tradition": rite.tradition,
            "church_id": rite.church_id,
            # Per-service variable declarations (RB-3b) so the wizard can
            # prompt for a rite's fields; empty for rites that declare none.
            "variables": [v.to_dict() for v in rite.variables],
        }

    @app.get("/api/rites")
    def list_rites(session: Session = Depends(session_dep)):
        require_user(session)
        stored = rites.list_rites(session.church_id)
        stored_ids = {r.id for r in stored}
        bundled = [r for r in rite_library.load_rites() if r.id not in stored_ids]
        return {"success": True,
                "rites": [_rite_summary(r) for r in bundled + stored]}

    def _known_modules(church_id: int) -> dict:
        modules = dict(rite_library.load_modules())
        for module in rites.list_modules(church_id):
            modules[module.id] = module
        return modules

    def _bundled_rite(rite_id: str):
        for rite in rite_library.load_rites():
            if rite.id == rite_id:
                return rite
        return None

    def _readable_rite(rite_id: str, session: Session):
        """A rite the caller may view: their own church's, or a library rite.

        Raises 404 if unknown, 403 if it belongs to another church.
        """
        rite = rites.get_rite(rite_id) or _bundled_rite(rite_id)
        if rite is None:
            raise _validation("That rite doesn't exist.", status=404)
        if rite.church_id is not None and rite.church_id != session.church_id:
            raise _validation("That rite isn't in your church.", status=403)
        return rite

    def _parse_rite_body(payload: dict, church_id: int) -> Rite:
        """Build a validated, church-owned Rite from a full editor payload."""
        payload = dict(payload)
        payload["church_id"] = church_id  # never trust the client's ownership
        try:
            rite = Rite.from_dict(payload)
        except RiteError as e:
            raise _validation("This rite has invalid structure: %s" % e)
        try:
            validate_rite(rite, modules=_known_modules(church_id))
        except RiteValidationError as e:
            raise _validation("This rite has errors: " + "; ".join(e.errors))
        return rite

    @app.post("/api/rites")
    def create_rite(payload: dict, session: Session = Depends(session_dep)):
        require_admin(session)
        from_rite_id = payload.get("from_rite_id")
        if from_rite_id:
            source = _readable_rite(from_rite_id, session)
            # base_rite_id must reference a persisted rite; bundled library
            # rites live only in JSON, so a library fork records no base link.
            base = from_rite_id if rites.get_rite(from_rite_id) else None
            forked = rites.fork_rite(source, session.church_id,
                                     name=payload.get("name"), base_rite_id=base)
            saved = rites.save_rite(forked)
            return {"success": True, "rite": saved.to_dict()}
        rite = _parse_rite_body(payload, session.church_id)
        saved = rites.save_rite(rite)
        return {"success": True, "rite": saved.to_dict()}

    @app.get("/api/rites/{rite_id}")
    def get_rite(rite_id: str, session: Session = Depends(session_dep)):
        require_user(session)
        rite = _readable_rite(rite_id, session)
        return {"success": True, "rite": rite.to_dict()}

    @app.put("/api/rites/{rite_id}")
    def update_rite(rite_id: str, payload: dict,
                    session: Session = Depends(session_dep)):
        require_admin(session)
        existing = rites.get_rite(rite_id)
        if existing is None and _bundled_rite(rite_id) is not None:
            raise _validation(
                "Library rites are read-only — fork a copy to edit it.",
                status=403)
        if existing is None:
            raise _validation("That rite doesn't exist in your church.",
                              status=404)
        if existing.church_id is None or existing.church_id != session.church_id:
            raise _validation(
                "Library rites are read-only — fork a copy to edit it."
                if existing.church_id is None
                else "That rite isn't in your church.",
                status=403 if existing.church_id is None else 404)
        payload = dict(payload)
        payload["id"] = rite_id
        rite = _parse_rite_body(payload, session.church_id)
        saved = rites.save_rite(rite)
        return {"success": True, "rite": saved.to_dict()}

    @app.delete("/api/rites/{rite_id}")
    def delete_rite(rite_id: str, session: Session = Depends(session_dep)):
        require_admin(session)
        existing = rites.get_rite(rite_id)
        if existing is None or existing.church_id != session.church_id:
            raise _validation("That rite isn't in your church.", status=404)
        if rites.rite_run_count(rite_id) > 0:
            raise _validation(
                "This rite is used by a saved past run — it can't be deleted.",
                status=409)
        rites.delete_rite(rite_id)
        return {"success": True}

    @app.post("/api/rites/{rite_id}/preview")
    def preview_rite(rite_id: str, payload: dict,
                     session: Session = Depends(session_dep)):
        require_user(session)
        rite = _readable_rite(rite_id, session)
        context = {
            "season": payload.get("season"),
            "feasts": payload.get("feasts") or [],
            "toggles": payload.get("toggles") or {},
        }
        visible = set(rites.visible_block_ids(rite, context))
        blocks = [
            {"id": b.id, "type": b.type, "title": b.title,
             "visible": b.id in visible}
            for b in rite.blocks
        ]
        return {"success": True, "blocks": blocks}

    def _rite_export_filename(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return f"{slug or 'rite'}.json"

    @app.get("/api/rites/{rite_id}/export")
    def export_rite(rite_id: str, session: Session = Depends(session_dep)):
        require_user(session)
        rite = _readable_rite(rite_id, session)
        body = json.dumps(rite.to_dict(), indent=2).encode("utf-8")
        filename = _rite_export_filename(rite.name)
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'},
        )

    async def _import_upload_bytes(request: Request) -> bytes:
        """Read the uploaded rite from either a multipart file or a raw body."""
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            if upload is None:
                raise _validation("No file was uploaded.")
            return await upload.read()
        return await request.body()

    @app.post("/api/rites/import")
    async def import_rite(request: Request,
                          session: Session = Depends(session_dep)):
        require_admin(session)
        raw = await _import_upload_bytes(request)
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise _validation(f"That file isn't valid JSON: {e}")
        if not isinstance(payload, dict):
            raise _validation("That file isn't a rite (expected a JSON object).")

        church_id = session.church_id
        try:
            rite = rites.prepare_import(payload, church_id)
        except RiteError as e:
            raise _validation(f"This file isn't a valid rite: {e}")
        try:
            validate_rite(rite, modules=_known_modules(church_id))
        except RiteValidationError as e:
            raise _validation("This rite has errors: " + "; ".join(e.errors))

        if rites.import_name_collides(rite.name, rite.occasion, church_id):
            payload = dict(payload)
            payload["name"] = rite.name + " (imported)"
            rite = rites.prepare_import(payload, church_id)

        saved = rites.save_rite(rite)
        return {"success": True, "rite": saved.to_dict()}

    # ── Rite canonical_slot sections (per-church fill / save / reuse) ────

    def _canonical_slot_blocks(rite) -> list:
        return [b for b in rite.blocks if b.type == "canonical_slot"]

    def _section_label(block) -> str:
        note = (block.note or "").strip()
        if note:
            return note
        return block.data["section_key"].replace("_", " ").title()

    def _section_status_context(session: Session) -> ContentContext:
        """A status-only content context: a whole-service S&S pull hook for an
        entitled church, else no hook (an unentitled church can't auto-fill)."""
        church = church_of(session)
        entitled = bool(church["sns_username"] and church["sns_password_enc"])
        sns_fetch_raw = (
            content_service(session).get_library_item_raw if entitled else None)
        return ContentContext(
            entitled=entitled, sns_fetch_raw=sns_fetch_raw, variables={})

    def _section_status(section_key: str, override_text, context) -> str:
        if override_text is not None:
            return "custom"
        if section_key not in SECTION_MAP:
            return "unmapped"
        return "s_and_s" if fill_section(section_key, context) is not None \
            else "needs_fill"

    def _require_canonical_section(rite, section_key: str) -> None:
        keys = {b.data["section_key"] for b in _canonical_slot_blocks(rite)}
        if section_key not in keys:
            raise _validation("That section isn't part of this rite.",
                              status=404)

    @app.get("/api/rites/{rite_id}/sections")
    def list_rite_sections(rite_id: str,
                           session: Session = Depends(session_dep)):
        require_user(session)
        rite = _readable_rite(rite_id, session)
        overrides = church_texts.section_overrides(session.church_id)
        context = _section_status_context(session)
        sections = []
        for block in _canonical_slot_blocks(rite):
            section_key = block.data["section_key"]
            override_text = overrides.get(section_key)
            sections.append({
                "section_key": section_key,
                "label": _section_label(block),
                "has_override": override_text is not None,
                "override_text": override_text,
                "status": _section_status(section_key, override_text, context),
            })
        return {"success": True, "sections": sections}

    @app.post("/api/rites/{rite_id}/sections/{section_key}")
    def save_rite_section(rite_id: str, section_key: str, payload: dict,
                          session: Session = Depends(session_dep)):
        require_admin(session)
        rite = _readable_rite(rite_id, session)
        _require_canonical_section(rite, section_key)
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise _validation("Enter some text before saving.")
        saved = church_texts.save_text(
            session.church_id, church_texts.OCCASION_SECTION_KIND,
            section_key, text)
        return {"success": True, "text": saved}

    @app.delete("/api/rites/{rite_id}/sections/{section_key}")
    def delete_rite_section(rite_id: str, section_key: str,
                            session: Session = Depends(session_dep)):
        require_admin(session)
        rite = _readable_rite(rite_id, session)
        _require_canonical_section(rite, section_key)
        rows = church_texts.list_texts(
            session.church_id, church_texts.OCCASION_SECTION_KIND)
        row = next((r for r in rows if r["name"] == section_key), None)
        if row is None:
            raise _validation("That section has no saved text.", status=404)
        church_texts.delete_text(session.church_id, row["id"])
        return {"success": True}

    # ── Day content ───────────────────────────────────────────────────

    @app.get("/api/day")
    def fetch_day(date: str, display: str, refresh: bool = False,
                  session: Session = Depends(session_dep)):
        require_user(session)
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
        except ValueError as e:
            raise _fail(422, e)
        service = content_service(session)
        try:
            api_date = f"{dt.year}-{dt.month}-{dt.day}"
            session.day = service.get_day_content(api_date, force_refresh=refresh)
            session.date_str = date
        except AuthError as e:
            session.close()
            raise _fail(502, BulletinError(
                "The linked Sundays & Seasons account was rejected — "
                f"an admin may need to re-link it. ({e})"))
        except BulletinError as e:
            raise _fail(502, e)

        day = session.day
        church = church_of(session)
        profile = profile_from_dict(json.loads(church["profile_json"]))
        provider = get_calendar_provider(profile.calendar_provider)
        liturgical_day = provider.resolve(date, day=day)
        season_id = liturgical_day.season.id
        seasonal = get_seasonal_config(season_id)
        return {
            "success": True,
            "title": day.title,
            "day_name": liturgical_day.day_name,
            "season": season_id,
            "readings": [
                {"label": r.label, "citation": r.citation} for r in day.readings
            ],
            "warnings": day.content_warnings(),
            "prefix": build_date_suffix(date, day.title),
            "defaults": {
                "creed_type": seasonal.creed_default,
                "include_kyrie": seasonal.has_kyrie,
                "canticle": seasonal.canticle,
                "eucharistic_form": seasonal.eucharistic_form,
                "include_memorial_acclamation": seasonal.has_memorial_acclamation,
                "preface": seasonal.preface.value,
                "show_confession": seasonal.show_confession,
                "show_nunc_dimittis": seasonal.show_nunc_dimittis,
            },
        }

    def _require_day(session: Session):
        require_user(session)
        if session.day is None:
            raise HTTPException(status_code=409, detail={
                "error": "No content fetched. Pick a date first.",
                "error_type": "validation",
            })
        return session.day

    @app.get("/api/day/texts")
    def liturgical_texts(session: Session = Depends(session_dep)):
        day = _require_day(session)
        saved = church_texts.texts_by_kind(session.church_id)
        return {"success": True,
                "texts": build_liturgical_text_options(day, saved)}

    @app.get("/api/day/readings/{slot}/preview")
    def reading_preview(slot: str, session: Session = Depends(session_dep)):
        day = _require_day(session)
        try:
            return {"success": True, **build_reading_preview(day, slot)}
        except (ValueError, BulletinError) as e:
            raise _fail(422, e)

    @app.post("/api/passage")
    def custom_passage(payload: dict, refresh: bool = False,
                       session: Session = Depends(session_dep)):
        require_user(session)
        service = content_service(session)
        citation = payload.get("citation", "")
        try:
            html = service.get_passage(citation, force_refresh=refresh)
        except BulletinError as e:
            raise _fail(502, e)
        return {"success": True, "text_html": html, "citation": citation}

    # ── Prefaces (static data) ────────────────────────────────────────

    @app.get("/api/prefaces")
    def prefaces():
        return {"success": True, "prefaces": get_preface_options()}

    # ── Hymns ─────────────────────────────────────────────────────────

    def _hymn_title_only(service: ContentService, collection: str,
                         number: str) -> dict:
        """Fallback for hymns with no downloadable words — needs the title."""
        try:
            results = service.search_hymn(number, collection)
        except BulletinError as e:
            raise _fail(502, e)
        if not results:
            raise HTTPException(status_code=404, detail={
                "error": f"No results for {collection} {number}",
                "error_type": "internal",
            })
        logger.warning("No lyrics for %s %s — title only", collection, number)
        return {
            "success": True,
            "number": f"{collection} {number}",
            "title": results[0].title,
            "verse_count": 0,
            "has_refrain": False,
            "lyrics_unavailable": True,
        }

    @app.get("/api/hymns/{collection}/{number}")
    def hymn(collection: str, number: str, date: str = "",
             refresh: bool = False,
             session: Session = Depends(session_dep)):
        """Search + fetch lyrics in one call (the SPA always does both)."""
        require_user(session)
        service = content_service(session)

        if date:
            try:
                dt = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                dt = datetime.now()
        else:
            dt = datetime.now()
        use_date = f"{dt.month}/{dt.day}/{dt.year}"

        # Some hymns have no downloadable words — degrade to title-only
        # rather than failing the whole slot.
        try:
            lyrics = service.get_hymn_lyrics(
                collection, number, use_date, force_refresh=refresh)
        except ContentNotFoundError:
            return _hymn_title_only(service, collection, number)
        except BulletinError as e:
            raise _fail(502, e)

        session.hymn_cache[f"{collection}_{number}"] = {
            "number": lyrics.number,
            "title": lyrics.title,
            "verses": lyrics.verses,
            "refrain": lyrics.refrain,
            "copyright": lyrics.copyright,
        }
        return {
            "success": True,
            "number": lyrics.number,
            "title": lyrics.title,
            "verse_count": len(lyrics.verses),
            "has_refrain": bool(lyrics.refrain),
        }

    # ── Cover upload ──────────────────────────────────────────────────

    @app.post("/api/cover")
    async def upload_cover(file: UploadFile,
                           session: Session = Depends(session_dep)):
        require_user(session)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_COVER_SUFFIXES:
            raise _validation(f"Unsupported image type: {suffix or '(none)'}")
        data = await file.read()
        if len(data) > MAX_COVER_BYTES:
            raise _validation("Cover image is too large (20 MB max).",
                              status=413)
        token = secrets.token_hex(8)
        dest = Path(tempfile.gettempdir()) / "bulletin-maker-covers"
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{session.id[:8]}_{token}{suffix}"
        path.write_bytes(data)
        return {"success": True, "cover_token": str(path)}

    # ── Generation jobs ───────────────────────────────────────────────

    def _store_results(church_id: int, job_id: str, results: dict) -> dict:
        store = artifacts.get_store()
        expires_at = artifacts.default_expiry()
        mapping = {}
        for doc_key, path in results.items():
            filename = Path(path).name
            object_key = f"{church_id}/{job_id}/{doc_key}/{filename}"
            num_bytes = store.put(object_key, path)
            artifacts.record_artifact(
                job_id, doc_key, filename, object_key, num_bytes, expires_at)
            mapping[doc_key] = filename
        return mapping

    def _run_job(session: Session, job_id: str, church_id: int,
                 form_data: dict, profile) -> None:
        observability.bind_context(job_id=job_id, church_id=church_id)
        job_dir = Path(tempfile.mkdtemp(prefix=f"bulletin-{job_id}-"))
        try:
            day = session.day
            config = build_service_config(form_data, session.hymn_cache)
            provider = get_calendar_provider(profile.calendar_provider)
            liturgical_day = provider.resolve(session.date_str, day=day)
            season_id = liturgical_day.season.id
            fill_seasonal_defaults(config, season_id)
            selected = set(form_data.get("selected_docs") or DEFAULT_SELECTION)

            def on_progress(key: str, detail: str, pct: int) -> None:
                jobstore.append_progress(
                    job_id, {"step": key, "detail": detail, "pct": pct})

            # Entitlement gate (CS-1): a validated S&S link resolves the ELW
            # wording; an unlinked church would fall back to PD/placeholder and
            # never receive copyrighted ELW text. Generation currently requires
            # a link (see the /api/generate guard), so this is True in practice.
            church = church_of(session)
            entitled = bool(church["sns_username"])

            # CS-2 pull hook: a closure over the church's content_service so
            # gap-fill keys resolve live from the church's S&S Library. Only an
            # entitled church has a client; the default path passes None.
            svc = content_service(session)
            sns_fetch = svc.get_library_item if entitled else None
            sns_fetch_raw = svc.get_library_item_raw if entitled else None

            # Per-church canonical_slot overrides (funeral / marriage sections):
            # keyed only by occasion section_keys, so no Sunday / office key is
            # shadowed and the parity path stays byte-identical.
            section_texts = church_texts.section_overrides(church_id)

            outcome = generate_documents(
                day, config, job_dir,
                season=season_id,
                client=session.client,
                selected=selected,
                on_progress=on_progress,
                profile=profile,
                entitled=entitled,
                church_texts=section_texts,
                sns_fetch=sns_fetch,
                sns_fetch_raw=sns_fetch_raw,
            )
            results = _store_results(church_id, job_id, outcome.results)
            status = "done" if outcome.success else "failed"
            jobstore.finish_job(job_id, status, results, outcome.errors)
        except Exception as e:
            logger.exception("Generation job failed")
            jobstore.finish_job(job_id, "failed", {}, {"job": str(e)})
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    @app.post("/api/generate")
    def generate(form_data: dict, session: Session = Depends(session_dep)):
        _require_day(session)
        church = church_of(session)
        plans.check_limit(church, "generate")
        if not form_data.get("date") or not form_data.get("date_display"):
            raise _validation("Missing required fields: date and date_display.")
        # A cache-hit day fetch never builds an S&S client, but generation
        # needs a live one (notation images) — build it before the worker.
        if not church["sns_username"] or not church["sns_password_enc"]:
            raise _sns_unlinked()
        _build_sns_client(session)
        profile = profile_from_dict(json.loads(church["profile_json"]))
        job_id = secrets.token_hex(8)
        try:
            artifacts.purge_expired_artifacts()
        except Exception:
            logger.exception("Opportunistic artifact purge failed")
        jobstore.create_job(
            job_id, session.church_id, session.user_id, form_data)
        worker = threading.Thread(
            target=_run_job,
            args=(session, job_id, session.church_id, form_data, profile),
            daemon=True)
        worker.start()
        return {"success": True, "job_id": job_id}

    def _load_job(session: Session, job_id: str) -> dict:
        require_user(session)
        job = jobstore.get_job(job_id, session.church_id)
        if job is None:
            raise _validation("Unknown job.", status=404)
        return job

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str, session: Session = Depends(session_dep)):
        job = _load_job(session, job_id)
        return {
            "success": True,
            "status": job["status"],
            "progress": job["progress_jsonb"],
            "results": job["results_jsonb"],
            "errors": job["errors_jsonb"],
        }

    @app.get("/api/jobs/{job_id}/files/{key}")
    def job_file(job_id: str, key: str,
                 session: Session = Depends(session_dep)):
        _load_job(session, job_id)
        artifact = artifacts.artifact_for_doc(job_id, key)
        if artifact is None:
            raise _validation(f"No file for document '{key}'.", status=404)
        filename = artifact["filename"]
        return StreamingResponse(
            artifacts.iter_object(artifact["object_key"]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/jobs/{job_id}/zip")
    def job_zip(job_id: str, session: Session = Depends(session_dep)):
        _load_job(session, job_id)
        rows = artifacts.artifacts_for_job(job_id)
        if not rows:
            raise _validation("No files to download.", status=404)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            for row in rows:
                zf.writestr(row["filename"],
                            artifacts.read_object(row["object_key"]))
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="bulletins.zip"'},
        )

    # ── Past runs (church-scoped) ─────────────────────────────────────

    @app.get("/api/runs")
    def list_runs(session: Session = Depends(session_dep)):
        require_user(session)
        return {"success": True, "runs": db.list_past_runs(session.church_id)}

    @app.post("/api/runs")
    def save_run(payload: dict, session: Session = Depends(session_dep)):
        require_user(session)
        run_id = db.save_past_run(
            session.church_id,
            payload.get("form_data", {}), payload.get("metadata", {}))
        return {"success": True, "id": run_id}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, session: Session = Depends(session_dep)):
        require_user(session)
        run = db.get_past_run(session.church_id, run_id)
        if run is None:
            raise _validation("Run not found.", status=404)
        return {"success": True,
                "form_data": run.get("form_data", {}),
                "metadata": run.get("metadata", {})}

    @app.delete("/api/runs/{run_id}")
    def delete_run(run_id: str, session: Session = Depends(session_dep)):
        require_user(session)
        if not db.delete_past_run(session.church_id, run_id):
            raise _validation("Run not found.", status=404)
        return {"success": True}

    # ── Operator console (cross-church) ───────────────────────────────

    @app.get("/api/operator/churches")
    def operator_churches(session: Session = Depends(session_dep)):
        require_operator(session)
        return {"success": True, "churches": operator.church_roster()}

    def _set_church_disabled(church_id: int, disabled: bool,
                             session: Session) -> dict:
        actor = require_operator(session)
        if not operator.set_church_disabled(church_id, disabled):
            raise _validation("Unknown church.", status=404)
        action = (operator.ACTION_CHURCH_DISABLED if disabled
                  else operator.ACTION_CHURCH_ENABLED)
        operator.audit(actor["id"], church_id, action, {})
        return {"success": True}

    @app.post("/api/operator/churches/{church_id}/disable")
    def operator_disable_church(church_id: int,
                                session: Session = Depends(session_dep)):
        return _set_church_disabled(church_id, True, session)

    @app.post("/api/operator/churches/{church_id}/enable")
    def operator_enable_church(church_id: int,
                               session: Session = Depends(session_dep)):
        return _set_church_disabled(church_id, False, session)

    @app.post("/api/operator/users/{user_id}/reset-password")
    def operator_reset_password(user_id: int,
                                session: Session = Depends(session_dep)):
        actor = require_operator(session)
        target = db.get_user(user_id)
        if target is None:
            raise _validation("Unknown user.", status=404)
        auth_flows.request_password_reset(target["email"])
        operator.audit(actor["id"], target["church_id"],
                       operator.ACTION_PASSWORD_RESET, {"user_id": user_id})
        return {"success": True}

    @app.get("/api/operator/jobs")
    def operator_jobs(session: Session = Depends(session_dep)):
        require_operator(session)
        return {"success": True, "jobs": operator.latest_jobs()}

    @app.get("/api/operator/cache")
    def operator_cache(session: Session = Depends(session_dep)):
        require_operator(session)
        return {"success": True, "cache": operator.cache_stats()}

    @app.get("/api/operator/audit")
    def operator_audit(session: Session = Depends(session_dep)):
        require_operator(session)
        return {"success": True, "events": operator.latest_audit()}

    # ── SPA ───────────────────────────────────────────────────────────

    app.mount("/", StaticFiles(directory=str(SPA_DIR), html=True), name="spa")

    return app
