"""POST /api/merge"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.routers.common import client_id
from app.schemas.video import JobCreatedResponse
from app.services.job_service import add_job_file, create_job
from app.services.upload import save_uploads
from app.workers.runner import runner
from app.workers.tasks import run_merge_job

router = APIRouter(prefix="/api", tags=["merge"])
settings = get_settings()


@router.post("/merge", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def merge_endpoint(
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    job = create_job(
        db,
        job_type="merge",
        params={"file_count": len(files)},
        client_id=client_id(request),
    )
    uploaded = await save_uploads(files, job.id, max_files=10)
    paths: list[Path] = []
    for item in uploaded:
        add_job_file(
            db,
            job_id=job.id,
            role="input",
            absolute_path=item.path,
            original_name=item.original_name,
            mime_type=item.content_type,
            part_index=item.index + 1,
            duration_seconds=item.info.duration,
            width=item.info.width,
            height=item.info.height,
            codec_video=item.info.codec_video,
            codec_audio=item.info.codec_audio,
        )
        paths.append(item.path)

    async def _factory() -> None:
        await run_merge_job(job.id, paths)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")
