"""VidKit FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import error_body, register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.rate_limit import limiter
from app.routers import (
    audio,
    compress,
    convert,
    extract,
    files,
    gif,
    health,
    image,
    jobs,
    merge,
    pdf,
    resize,
    rotate,
    split,
    trim,
    video,
)
from app.services.job_service import mark_stale_processing_jobs
from app.services.storage import ensure_storage_dirs
from app.workers.cleanup import start_cleanup_scheduler, stop_cleanup_scheduler
from app.workers.runner import runner

settings = get_settings()
setup_logging(settings.app_env)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    import os

    ensure_storage_dirs(settings)
    db = SessionLocal()
    try:
        stale = mark_stale_processing_jobs(db)
        if stale:
            logger.info("marked_stale_jobs", count=stale)
    except Exception:  # noqa: BLE001
        logger.warning("stale_job_check_skipped")
    finally:
        db.close()

    disable_bg = os.environ.get("VIDKIT_DISABLE_SCHEDULER") == "1"
    if not disable_bg:
        await runner.start()
        start_cleanup_scheduler()
    logger.info("app_started", env=settings.app_env)
    yield
    if not disable_bg:
        stop_cleanup_scheduler()
        await runner.stop()
    logger.info("app_stopped")


app = FastAPI(
    title="VidKit API",
    description=(
        "VidKit video tools API.\n\n"
        "**Legal notice:** Only download or process content you own or have "
        "permission to use. Respect platform Terms of Service and copyright law."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_request: Request, _exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content=error_body("RATE_LIMITED", "Too many requests. Please try again later."),
    )


app.include_router(health.router)
app.include_router(video.router)
app.include_router(split.router)
app.include_router(compress.router)
app.include_router(extract.router)
app.include_router(trim.router)
app.include_router(convert.router)
app.include_router(merge.router)
app.include_router(gif.router)
app.include_router(rotate.router)
app.include_router(resize.router)
app.include_router(image.router)
app.include_router(pdf.router)
app.include_router(audio.router)
app.include_router(jobs.router)
app.include_router(files.router)
