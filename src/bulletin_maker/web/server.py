"""FastAPI application — the web adapter over the core layer.

Endpoints mirror the wizard's needs. Generation runs as a background
job in a worker thread (Playwright's sync API); the SPA polls the job
for progress and downloads the finished PDFs.
"""

from __future__ import annotations

import logging
import os
import secrets
import tempfile
import time
import threading
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
from bulletin_maker.core.profile import load_profile
from bulletin_maker.core.service_form import build_service_config
from bulletin_maker.exceptions import AuthError, BulletinError, NetworkError
from bulletin_maker.renderer.season import (
    detect_season,
    fill_seasonal_defaults,
    get_preface_options,
    get_seasonal_config,
)
from bulletin_maker.web.sessions import SESSION_COOKIE, Session, SessionStore

logger = logging.getLogger(__name__)

SPA_DIR = Path(__file__).resolve().parents[1] / "ui" / "templates"

ALLOWED_COVER_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MAX_COVER_BYTES = 20 * 1024 * 1024


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


LOGIN_ATTEMPT_LIMIT = 10
LOGIN_ATTEMPT_WINDOW_SECONDS = 300


class LoginRateLimiter:
    """Per-address sliding-window limiter for the login endpoint."""

    def __init__(self, limit: int = LOGIN_ATTEMPT_LIMIT,
                 window: float = LOGIN_ATTEMPT_WINDOW_SECONDS) -> None:
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


def create_app() -> FastAPI:
    app = FastAPI(title="Bulletin Maker", docs_url=None, redoc_url=None)
    store = SessionStore()
    hosted = os.environ.get("BULLETIN_HOSTED") == "1"
    login_limiter = LoginRateLimiter()

    def session_dep(request: Request, response: Response) -> Session:
        sid = request.cookies.get(SESSION_COOKIE)
        session = store.get_or_create(sid)
        if session.id != sid:
            response.set_cookie(
                SESSION_COOKIE, session.id,
                httponly=True, samesite="lax", secure=hosted,
            )
        return session

    # ── Profile ───────────────────────────────────────────────────────

    @app.get("/api/profile")
    def get_profile():
        profile = load_profile()
        return {
            "success": True,
            "church_name": profile.church_name,
            "service_time": profile.service_time,
            "source_path": profile.source_path,
        }

    # ── Auth ──────────────────────────────────────────────────────────

    @app.post("/api/session")
    def login(payload: dict, request: Request,
              session: Session = Depends(session_dep)):
        if hosted:
            address = request.client.host if request.client else "unknown"
            if not login_limiter.check(address):
                raise HTTPException(status_code=429, detail={
                    "error": "Too many sign-in attempts — wait a few minutes.",
                    "error_type": "validation",
                })
        username = payload.get("username", "")
        password = payload.get("password", "")
        try:
            session.get_client().login(username, password)
        except AuthError as e:
            raise _fail(401, e)
        except BulletinError as e:
            raise _fail(502, e)
        return {"success": True, "username": username}

    @app.delete("/api/session")
    def logout(session: Session = Depends(session_dep)):
        session.close()
        session.day = None
        session.date_str = None
        session.hymn_cache.clear()
        return {"success": True}

    # ── Day content ───────────────────────────────────────────────────

    @app.get("/api/day")
    def fetch_day(date: str, display: str,
                  session: Session = Depends(session_dep)):
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
        except ValueError as e:
            raise _fail(422, e)
        try:
            api_date = f"{dt.year}-{dt.month}-{dt.day}"
            session.day = session.get_client().get_day_texts(api_date)
            session.date_str = date
        except AuthError as e:
            raise _fail(401, e)
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
    def custom_passage(payload: dict, session: Session = Depends(session_dep)):
        citation = payload.get("citation", "")
        try:
            html = session.get_client().search_passage(citation)
        except AuthError as e:
            raise _fail(401, e)
        except BulletinError as e:
            raise _fail(502, e)
        return {"success": True, "text_html": html, "citation": citation}

    # ── Prefaces (static data) ────────────────────────────────────────

    @app.get("/api/prefaces")
    def prefaces():
        return {"success": True, "prefaces": get_preface_options()}

    # ── Hymns ─────────────────────────────────────────────────────────

    @app.get("/api/hymns/{collection}/{number}")
    def hymn(collection: str, number: str, date: str = "",
             session: Session = Depends(session_dep)):
        """Search + fetch lyrics in one call (the SPA always does both)."""
        client = session.get_client()
        try:
            results = client.search_hymn(number, collection)
            if not results:
                raise HTTPException(status_code=404, detail={
                    "error": f"No results for {collection} {number}",
                    "error_type": "internal",
                })
            found = results[0]
            if date:
                try:
                    dt = datetime.strptime(date, "%Y-%m-%d")
                except ValueError:
                    dt = datetime.now()
            else:
                dt = datetime.now()
            use_date = f"{dt.month}/{dt.day}/{dt.year}"
            lyrics = client.fetch_hymn_lyrics(number, use_date, collection)
        except AuthError as e:
            raise _fail(401, e)
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
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_COVER_SUFFIXES:
            raise HTTPException(status_code=422, detail={
                "error": f"Unsupported image type: {suffix or '(none)'}",
                "error_type": "validation",
            })
        data = await file.read()
        if len(data) > MAX_COVER_BYTES:
            raise HTTPException(status_code=413, detail={
                "error": "Cover image is too large (20 MB max).",
                "error_type": "validation",
            })
        token = secrets.token_hex(8)
        dest = Path(tempfile.gettempdir()) / "bulletin-maker-covers"
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{session.id[:8]}_{token}{suffix}"
        path.write_bytes(data)
        return {"success": True, "cover_token": str(path)}

    # ── Generation jobs ───────────────────────────────────────────────

    def _run_job(session: Session, job: dict, form_data: dict) -> None:
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
            raise HTTPException(status_code=422, detail={
                "error": "Missing required fields: date and date_display.",
                "error_type": "validation",
            })
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
            target=_run_job, args=(session, job, form_data), daemon=True)
        worker.start()
        return {"success": True, "job_id": job_id}

    def _get_job(session: Session, job_id: str) -> dict:
        job = session.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail={
                "error": "Unknown job.", "error_type": "validation"})
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
            raise HTTPException(status_code=404, detail={
                "error": f"No file for document '{key}'.",
                "error_type": "validation"})
        path = Path(job["dir"]) / filename
        return FileResponse(path, filename=filename, media_type="application/pdf")

    @app.get("/api/jobs/{job_id}/zip")
    def job_zip(job_id: str, session: Session = Depends(session_dep)):
        job = _get_job(session, job_id)
        if not job["results"]:
            raise HTTPException(status_code=404, detail={
                "error": "No files to download.", "error_type": "validation"})
        zip_path = Path(job["dir"]) / "bulletins.zip"
        if not zip_path.exists():
            with zipfile.ZipFile(zip_path, "w") as zf:
                for filename in job["results"].values():
                    zf.write(Path(job["dir"]) / filename, arcname=filename)
        return FileResponse(zip_path, filename="bulletins.zip",
                            media_type="application/zip")

    # ── Past runs (server-side store, same location as desktop) ──────

    from bulletin_maker.web.past_runs import router as past_runs_router
    app.include_router(past_runs_router)

    # ── SPA ───────────────────────────────────────────────────────────

    app.mount("/", StaticFiles(directory=str(SPA_DIR), html=True), name="spa")

    return app
