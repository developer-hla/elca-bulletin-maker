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

import json
import logging
import os
import secrets
import tempfile
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bulletin_maker.core.content_views import (
    build_liturgical_text_options,
    build_reading_preview,
)
from bulletin_maker.core.documents import DEFAULT_SELECTION, generate_documents
from bulletin_maker.core.naming import build_date_suffix, extract_day_name
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
    detect_season,
    fill_seasonal_defaults,
    get_preface_options,
    get_seasonal_config,
)
from bulletin_maker.renderer.settings import SETTINGS
from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.sns.content_service import ContentService
from bulletin_maker.web import db, security
from bulletin_maker.web.sessions import SESSION_COOKIE, Session, SessionStore

logger = logging.getLogger(__name__)

SPA_DIR = Path(__file__).resolve().parents[1] / "ui" / "templates"

ALLOWED_COVER_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MAX_COVER_BYTES = 20 * 1024 * 1024
MIN_PASSWORD_LENGTH = 8

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
    app = FastAPI(title="Bulletin Maker", docs_url=None, redoc_url=None)
    store = SessionStore()
    hosted = os.environ.get("BULLETIN_HOSTED") == "1"
    limiter = LoginRateLimiter()

    def session_dep(request: Request, response: Response) -> Session:
        sid = request.cookies.get(SESSION_COOKIE)
        session = store.get_or_create(sid)
        if session.id != sid:
            response.set_cookie(
                SESSION_COOKIE, session.id,
                httponly=True, samesite="lax", secure=hosted,
            )
        return session

    def require_user(session: Session) -> dict:
        if session.user_id is None:
            raise _auth_required()
        user = db.get_user(session.user_id)
        if user is None:
            session.sign_out()
            raise _auth_required()
        return user

    def require_admin(session: Session) -> dict:
        user = require_user(session)
        if user["role"] != "admin":
            raise _validation("Only a church admin can do that.", status=403)
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

    def _sign_in(session: Session, user: dict) -> dict:
        session.sign_out()
        session.user_id = user["id"]
        session.church_id = user["church_id"]
        church = db.get_church(user["church_id"])
        return {
            "success": True,
            "user": {"email": user["email"],
                     "display_name": user["display_name"],
                     "role": user["role"]},
            "church": {"name": church["name"]},
            "sns_linked": bool(church["sns_username"]),
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
    def register(payload: dict, request: Request,
                 session: Session = Depends(session_dep)):
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
        return _sign_in(session, user)

    @app.post("/api/join")
    def join(payload: dict, request: Request,
             session: Session = Depends(session_dep)):
        _check_rate(request)
        invite_code = (payload.get("invite_code") or "").strip()
        church = db.get_church_by_invite(invite_code) if invite_code else None
        if church is None:
            raise _validation("That invite code isn't valid.", status=403)
        email, password, display_name = _validate_account_fields(payload)
        if db.get_user_by_email(email) is not None:
            raise _validation("That email already has an account.", status=409)
        user = db.create_user(
            church["id"], email, security.hash_password(password),
            display_name, role="member")
        return _sign_in(session, user)

    # ── App sessions ──────────────────────────────────────────────────

    @app.post("/api/session")
    def login(payload: dict, request: Request,
              session: Session = Depends(session_dep)):
        _check_rate(request)
        email = (payload.get("email") or "").strip()
        password = payload.get("password") or ""
        user = db.get_user_by_email(email)
        if user is None or not security.verify_password(
                password, user["password_hash"]):
            raise HTTPException(status_code=401, detail={
                "error": "Email or password is incorrect.",
                "error_type": "auth"})
        return _sign_in(session, user)

    @app.get("/api/session")
    def whoami(session: Session = Depends(session_dep)):
        if session.user_id is None:
            return {"success": True, "authenticated": False}
        user = db.get_user(session.user_id)
        if user is None:
            session.sign_out()
            return {"success": True, "authenticated": False}
        church = db.get_church(user["church_id"])
        return {
            "success": True,
            "authenticated": True,
            "user": {"email": user["email"],
                     "display_name": user["display_name"],
                     "role": user["role"]},
            "church": {"name": church["name"]},
            "sns_linked": bool(church["sns_username"]),
        }

    @app.delete("/api/session")
    def logout(session: Session = Depends(session_dep)):
        session.sign_out()
        return {"success": True}

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
        for field in PROFILE_FIELDS:
            if field in payload:
                profile[field] = payload[field]
        if profile.get("liturgical_setting") not in SETTINGS:
            raise _validation("Choose a liturgical setting from the list.")
        if profile.get("paper_size") not in PAPER_PRESETS:
            raise _validation("Choose a paper size from the list.")
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
        require_admin(session)
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
        return {"success": True, "sns_username": username}

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
        season = detect_season(day.title)
        seasonal = get_seasonal_config(season)
        return {
            "success": True,
            "title": day.title,
            "day_name": extract_day_name(day.title),
            "season": season.value,
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
        return {"success": True, "texts": build_liturgical_text_options(day)}

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

    def _run_job(session: Session, job: dict, form_data: dict,
                 profile) -> None:
        try:
            day = session.day
            config = build_service_config(form_data, session.hymn_cache)
            season = detect_season(day.title)
            fill_seasonal_defaults(config, season)
            selected = set(form_data.get("selected_docs") or DEFAULT_SELECTION)

            def on_progress(key: str, detail: str, pct: int) -> None:
                job["progress"].append(
                    {"step": key, "detail": detail, "pct": pct})

            outcome = generate_documents(
                day, config, Path(job["dir"]),
                season=season,
                client=session.client,
                selected=selected,
                on_progress=on_progress,
                profile=profile,
            )
            job["results"] = {
                key: Path(path).name for key, path in outcome.results.items()
            }
            job["errors"] = outcome.errors
            job["status"] = "done" if outcome.success else "failed"
        except Exception as e:
            logger.exception("Generation job failed")
            job["errors"] = {"job": str(e)}
            job["status"] = "failed"

    @app.post("/api/generate")
    def generate(form_data: dict, session: Session = Depends(session_dep)):
        _require_day(session)
        if not form_data.get("date") or not form_data.get("date_display"):
            raise _validation("Missing required fields: date and date_display.")
        profile = profile_from_dict(
            json.loads(church_of(session)["profile_json"]))
        job_id = secrets.token_hex(8)
        job_dir = tempfile.mkdtemp(prefix=f"bulletin-{job_id}-")
        job = {
            "id": job_id,
            "status": "running",
            "progress": [],
            "results": {},
            "errors": {},
            "dir": job_dir,
        }
        session.jobs[job_id] = job
        worker = threading.Thread(
            target=_run_job, args=(session, job, form_data, profile),
            daemon=True)
        worker.start()
        return {"success": True, "job_id": job_id}

    def _get_job(session: Session, job_id: str) -> dict:
        require_user(session)
        job = session.jobs.get(job_id)
        if job is None:
            raise _validation("Unknown job.", status=404)
        return job

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str, session: Session = Depends(session_dep)):
        job = _get_job(session, job_id)
        return {
            "success": True,
            "status": job["status"],
            "progress": job["progress"],
            "results": job["results"],
            "errors": job["errors"],
        }

    @app.get("/api/jobs/{job_id}/files/{key}")
    def job_file(job_id: str, key: str,
                 session: Session = Depends(session_dep)):
        job = _get_job(session, job_id)
        filename = job["results"].get(key)
        if not filename:
            raise _validation(f"No file for document '{key}'.", status=404)
        path = Path(job["dir"]) / filename
        return FileResponse(path, filename=filename, media_type="application/pdf")

    @app.get("/api/jobs/{job_id}/zip")
    def job_zip(job_id: str, session: Session = Depends(session_dep)):
        job = _get_job(session, job_id)
        if not job["results"]:
            raise _validation("No files to download.", status=404)
        zip_path = Path(job["dir"]) / "bulletins.zip"
        if not zip_path.exists():
            with zipfile.ZipFile(zip_path, "w") as zf:
                for filename in job["results"].values():
                    zf.write(Path(job["dir"]) / filename, arcname=filename)
        return FileResponse(zip_path, filename="bulletins.zip",
                            media_type="application/zip")

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

    # ── SPA ───────────────────────────────────────────────────────────

    app.mount("/", StaticFiles(directory=str(SPA_DIR), html=True), name="spa")

    return app
