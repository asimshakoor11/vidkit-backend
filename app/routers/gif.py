"""POST /api/gif"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.routers.common import client_id
from app.schemas.video import JobCreatedResponse
from app.services.job_service import add_job_file, create_job
from app.services.upload import save_upload
from app.workers.runner import runner
from app.workers.tasks import run_gif_job

router = APIRouter(prefix="/api", tags=["gif"])
settings = get_settings()


@router.post("/gif", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def gif_endpoint(
    request: Request,
    file: UploadFile = File(...),
    start: float = Form(0),
    duration: float = Form(5),
    width: int = Form(480),
    fps: int = Form(10),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if width < 64 or width > 1920:
        raise AppError("UNSUPPORTED_FORMAT", "Width must be between 64 and 1920.")
    if fps < 8 or fps > 15:
        raise AppError("UNSUPPORTED_FORMAT", "FPS must be between 8 and 15.")
    if duration <= 0 or duration > 60:
        raise AppError("INVALID_RANGE", "GIF duration must be between 0 and 60 seconds.")

    job = create_job(
        db,
        job_type="gif",
        params={"start": start, "duration": duration, "width": width, "fps": fps},
        client_id=client_id(request),
    )
    uploaded = await save_upload(file, job.id)
    if start < 0 or start >= uploaded.info.duration:
        raise AppError("INVALID_RANGE", "Start time is outside the video.")
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

    async def _factory() -> None:
        await run_gif_job(job.id, uploaded.path, start, duration, width, fps)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")
