"""
TechScape AI — FastAPI Application Entry Point
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core import error_tracking
from app.routers import api_router
from app.routers.travel import calls_ws_router

# Logging configuration
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — startup launches the optional webhook worker."""
    error_tracking.init()
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")
    stop_event: asyncio.Event = asyncio.Event()
    worker_task: asyncio.Task | None = None
    alert_task: asyncio.Task | None = None
    if os.environ.get("ENABLE_WEBHOOK_WORKER") == "1":
        try:
            from app.services.techscape.webhook_worker import run_loop  # local import
            worker_task = asyncio.create_task(run_loop(stop_event))
            logger.info("TechScape webhook worker launched")
        except Exception:
            logger.exception("failed to start webhook worker")
    # Observability: alerting rules as code (app/core/alerting.py). OFF by
    # default — evaluates only when OBSERVABILITY_ALERTS=true. Fired rules go
    # through error_tracking.capture_message (stub transport until a DSN exists).
    if settings.OBSERVABILITY_ALERTS:
        try:
            from app.core import alerting  # local import: zero cost when disabled
            alert_task = asyncio.create_task(alerting.run_alert_loop(stop_event))
            logger.info("Observability alert loop launched")
        except Exception:
            logger.exception("failed to start alert loop")
    try:
        yield
    finally:
        stop_event.set()
        for task in (worker_task, alert_task):
            if task is not None:
                try:
                    await asyncio.wait_for(task, timeout=5)
                except Exception:
                    pass
        logger.info("Application shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered platform for navigating the technology landscape.",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ──────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    # Vercel preview hostnames change every deploy — see ALLOWED_ORIGIN_REGEX.
    allow_origin_regex=settings.ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
app.include_router(api_router, prefix="/api")
# No /api prefix, deliberately — matches gogaga-verifier/scripts/
# ws_probe.py and the api-contract.md target: ws://<host>/ws/calls/{id}.
app.include_router(calls_ws_router)


# ──────────────────────────────────────────────
# Global exception handler
# ──────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # Strip `input` and `ctx` to prevent echoing submitted field values
    # (e.g. plaintext passwords) in 422 validation error responses.
    def _scrub(err: dict) -> dict:
        return {k: v for k, v in err.items() if k not in ("input", "ctx")}
    return JSONResponse(
        status_code=422,
        content={"detail": [_scrub(e) for e in exc.errors()]},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    # Observability: one stable capture point for every unhandled exception.
    # Stub transport without SENTRY_DSN — logged + counted, nothing leaves.
    error_tracking.capture_exception(exc, context={"path": str(request.url.path)})
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again."},
    )
