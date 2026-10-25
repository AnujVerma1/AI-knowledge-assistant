"""FastAPI application factory.

Run locally from the backend folder:
    uvicorn app.main:app --reload --port 8001
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api import auth, conversations, documents, health
from app.api.deps import get_storage, get_vector_store
from app.api.errors import error_response, register_exception_handlers
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_session_factory
from app.services import documents as documents_service

logger = logging.getLogger("app.request")

# Multipart framing adds a little on top of the file itself.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


async def log_requests(request: Request, call_next):
    request_id = uuid.uuid4().hex
    structlog.contextvars.bind_contextvars(request_id=request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
    # Only method and path are logged: query strings and bodies may contain personal data.
    logger.info(
        "request",
        extra={"method": request.method, "path": request.url.path, "status": response.status_code, "duration_ms": duration_ms},
    )
    response.headers["X-Request-ID"] = request_id
    # API responses are private to one user: no browser, proxy or CDN (e.g. Vercel's rewrite
    # cache) may store them and serve them to someone else.
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
    structlog.contextvars.clear_contextvars()
    return response


async def reject_oversized_uploads(request: Request, call_next):
    """Refuse uploads whose declared size is too large before the body is read."""
    if request.method == "POST" and request.url.path == "/api/documents":
        limit = get_settings().max_upload_bytes + _MULTIPART_OVERHEAD_BYTES
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            return error_response(413, "payload_too_large", f"Files can be at most {get_settings().max_upload_mb} MB.")
    return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    overrides = app.dependency_overrides

    def recover() -> None:
        documents_service.recover_interrupted(
            overrides.get(get_session_factory, get_session_factory)(),
            storage=overrides.get(get_storage, get_storage)(),
            vector_store=overrides.get(get_vector_store, get_vector_store)(),
        )

    try:
        await run_in_threadpool(recover)
    except Exception:
        # The API should still start (e.g. to serve /api/health) if a dependency is down.
        logging.getLogger(__name__).warning("Startup recovery of interrupted documents was skipped", exc_info=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env == "production")
    is_production = settings.app_env == "production"

    app = FastAPI(
        title="AI Knowledge Base Assistant API",
        version="0.1.0",
        docs_url=None if is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if is_production else "/api/openapi.json",
        lifespan=lifespan,
    )
    app.middleware("http")(reject_oversized_uploads)
    app.middleware("http")(log_requests)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    register_exception_handlers(app)
    for router in (health.router, auth.router, documents.router, conversations.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
