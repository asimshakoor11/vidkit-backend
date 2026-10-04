"""Video split upload and URL routes."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.core.security import detect_platform_from_url
from app.routers.common import client_id
from app.schemas.split import SplitFromUrlRequest
from app.schemas.video import JobCreatedResponse
from app.services import downloader as downloader_service
from app.services.job_service import add_job_file, create_job
from app.services.upload import save_upload
from app.workers.runner import runner
from app.workers.tasks import run_download_split_job, run_split_job

router = APIRouter(prefix="/api", tags=["split"])
settings = get_settings()


def _validate_split_params(chunk_seconds: int, mode: str) -> None:
    if mode not in {"fast", "precise"}:
        raise AppError("INVALID_CHUNK_LENGTH", "Mode must be 'fast' or 'precise'.")
    if chunk_seconds < 1:
        raise AppError("INVALID_CHUNK_LENGTH", "Chunk length must be at least 1 second.")


@router.post("/split", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def split_endpoint(
    request: Request,
    file: UploadFile = File(...),
    chunk_seconds: int = Form(...),
    mode: str = Form(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    """Accept a video upload and queue a split job."""
    _validate_split_params(chunk_seconds, mode)

    job = create_job(
        db,
        job_type="split",
        params={
            "chunk_seconds": chunk_seconds,
            "mode": mode,
            "original_name": file.filename or "video.mp4",
        },
        client_id=client_id(request),
    )

    uploaded = await save_upload(file, job.id)
    if chunk_seconds >= uploaded.info.duration:
        raise AppError(
            "INVALID_CHUNK_LENGTH",
            "Chunk length must be shorter than the video duration.",
        )

    add_job_file(
        db,
        job_id=job.id,
        role="input",
        absolute_path=uploaded.path,
        original_name=uploaded.original_name,
        mime_type=uploaded.content_type,
        duration_seconds=uploaded.info.duration,
        width=uploaded.info.width,
        height=uploaded.info.height,
        codec_video=uploaded.info.codec_video,
        codec_audio=uploaded.info.codec_audio,
    )

    input_path = Path(uploaded.path)

    async def _factory() -> None:
        await run_split_job(job.id, input_path, chunk_seconds, mode)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/split/from-url", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def split_from_url(
    request: Request,
    body: SplitFromUrlRequest,
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    """Download a video from a URL, then queue a split job."""
    if body.format_id == "audio":
        raise AppError(
            "UNSUPPORTED_FORMAT",
            "Audio-only format cannot be split; choose a video quality.",
        )

    _validate_split_params(body.chunk_seconds, body.mode)
    platform = detect_platform_from_url(body.url)
    downloader_service.format_selector(body.format_id)

    info = await asyncio.to_thread(downloader_service.extract_info, body.url)
    if info.duration_seconds > 0:
        if info.duration_seconds > settings.max_video_duration_seconds:
            raise AppError(
                "DURATION_LIMIT",
                f"Video exceeds the {settings.max_video_duration_min} minute limit.",
            )
        if body.chunk_seconds >= info.duration_seconds:
            raise AppError(
                "INVALID_CHUNK_LENGTH",
                "Chunk length must be shorter than the video duration.",
            )

    video_formats = [f for f in info.formats if f.kind == "video"]
    if not video_formats:
        raise AppError(
            "UNSUPPORTED_FORMAT",
            "No downloadable video formats found for this URL.",
        )
    if not any(f.format_id == body.format_id for f in video_formats):
        raise AppError("UNSUPPORTED_FORMAT", f"Unknown format: {body.format_id}")

    job = create_job(
        db,
        job_type="download_split",
        params={
            "url": body.url,
            "format_id": body.format_id,
            "chunk_seconds": body.chunk_seconds,
            "mode": body.mode,
            "title": info.title,
        },
        platform=platform,
        source_url=body.url,
        client_id=client_id(request),
    )

    async def _factory() -> None:
        await run_download_split_job(
            job.id,
            body.url,
            body.format_id,
            body.chunk_seconds,
            body.mode,
        )

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")
