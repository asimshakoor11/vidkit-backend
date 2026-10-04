"""POST /api/convert"""

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
from app.workers.tasks import run_convert_job

router = APIRouter(prefix="/api", tags=["convert"])
settings = get_settings()


@router.post("/convert", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def convert_endpoint(
    request: Request,
    file: UploadFile = File(...),
    target: str = Form(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if target not in {"mp4", "mov", "webm", "mkv", "avi"}:
        raise AppError("UNSUPPORTED_FORMAT", "Target must be mp4, mov, webm, mkv, or avi.")

    job = create_job(
        db,
        job_type="convert",
        params={"target": target},
        client_id=client_id(request),
    )
    uploaded = await save_upload(file, job.id)
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
        await run_convert_job(job.id, uploaded.path, target)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")
