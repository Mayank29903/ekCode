import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.datastructures import MutableHeaders

from .config import check_secrets, settings
from .db import SessionLocal
from .routers import admin, analytics, audit_log, auth, graph, ingest, integrations, materials, review, search

logging.basicConfig(level=getattr(logging, settings.log_level.strip().upper(), logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ekcode")
RETRYABLE = {"40P01", "40001"}      # deadlock detected, serialization failure


def load_dictionary() -> None:
    from ekml.normalize import set_abbreviations

    from .settings_store import get_setting
    with SessionLocal() as db:
        set_abbreviations(get_setting(db, "abbreviations"))    # empty -> the shipped YAML


@asynccontextmanager
async def lifespan(_app: FastAPI):
    check_secrets()
    load_dictionary()
    yield


class NoStoreMiddleware:
    """Authenticated API responses must not be kept by browser or proxy caches (ASVS 8.2.1).
    Pure ASGI (not BaseHTTPMiddleware), so streaming responses such as SSE pass through untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])       # optional in ASGI; MutableHeaders needs the key
                MutableHeaders(scope=message).setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_with_header)


app = FastAPI(title="EkCode API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs" if settings.docs_enabled else None,
              openapi_url="/api/openapi.json" if settings.docs_enabled else None, redoc_url=None)
app.add_middleware(NoStoreMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth, ingest, review, materials, search, analytics, graph, audit_log, integrations, admin):
    app.include_router(r.router, prefix="/api/v1")


@app.exception_handler(IntegrityError)
async def integrity_error(_request: Request, exc: IntegrityError):
    """Two requests raced for the same row (e.g. both mapping one legacy code): a clean 409, not a 500."""
    log.warning("integrity error: %s", exc.orig)
    return JSONResponse({"detail": "This change conflicts with one that was just saved. Refresh and try again."},
                        status_code=409)


@app.exception_handler(OperationalError)
async def operational_error(_request: Request, exc: OperationalError):
    if getattr(exc.orig, "sqlstate", None) in RETRYABLE:
        return JSONResponse({"detail": "Another change touched the same records at the same moment. Try again."},
                            status_code=409)
    log.error("database error: %s", exc)
    return JSONResponse({"detail": "The database is not reachable right now. Try again in a moment."},
                        status_code=503)


@app.get("/api/v1/health")
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"ok": False, "db": "unreachable"}, status_code=503)
    return {"ok": True}
