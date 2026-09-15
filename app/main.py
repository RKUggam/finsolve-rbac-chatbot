"""FastAPI application entry point.

Wires together auth, chat API, the web UI, health probes, and Prometheus metrics,
plus request-scoped structured logging with a correlation id.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.api.chat import router as chat_router
from app.auth.router import router as auth_router
from app.config import get_settings
from app.logging_config import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)
from app.monitoring.cost import cost_tracker
from app.web import router as web_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    configure_logging()
    settings = get_settings()
    settings.validate_runtime()
    logger.info(
        "app_startup",
        version=__version__,
        env=settings.app_env,
        azure_configured=settings.azure_openai_configured,
    )
    yield
    logger.info("app_shutdown")


app = FastAPI(
    title="FinSolve RBAC RAG Chatbot",
    version=__version__,
    description="Internal knowledge assistant with role-based access control.",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):  # noqa: ANN001, ANN201
    """Attach a correlation id and log request lifecycle."""
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    bind_request_context(request_id=request_id, path=request.url.path, method=request.method)
    try:
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        logger.info("request_completed", status_code=response.status_code)
        return response
    except Exception:
        logger.exception("request_failed")
        raise
    finally:
        clear_request_context()


# ---- Routers ----
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(web_router)

# ---- Static assets ----
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ---- Health & readiness probes (used by Azure Container Apps) ----
@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness probe — the process is up."""
    return {"status": "ok", "version": __version__}


@app.get("/ready", tags=["ops"])
def ready() -> JSONResponse:
    """Readiness probe — dependencies configured."""
    settings = get_settings()
    ok = settings.azure_openai_configured
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": "ready" if ok else "degraded",
            "azure_openai": settings.azure_openai_configured,
            "daily_cost_usd": cost_tracker.daily_cost,
        },
    )


@app.get("/metrics", tags=["ops"])
def metrics_endpoint() -> Response:
    """Prometheus metrics scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
