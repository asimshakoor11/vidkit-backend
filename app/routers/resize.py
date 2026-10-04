"""POST /api/resize"""

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
from app.workers.tasks import run_resize_job

router = APIRouter(prefix="/api", tags=["resize"])
settings = get_settings()


@router.post("/resize", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def resize_endpoint(
    request: Request,
    file: UploadFile = File(...),
    preset: str | None = Form(None),
    width: int | None = Form(None),
    height: int | None = Form(None),
    fit: str = Form("contain"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if fit not in {"contain", "cover"}:
        raise AppError("UNSUPPORTED_FORMAT", "Fit must be contain or cover.")
    if not preset and (not width or not height):
        raise AppError("UNSUPPORTED_FORMAT", "Provide a preset or width and height.")

    job = create_job(
        db,
        job_type="resize",
        params={"preset": preset, "width": width, "height": height, "fit": fit},
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
        await run_resize_job(job.id, uploaded.path, preset, width, height, fit)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")
