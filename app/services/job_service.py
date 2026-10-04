"""Job lifecycle helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.job import Job
from app.models.job_file import JobFile
from app.schemas.job import JobOutputOut, JobStatusResponse
from app.services.storage import delete_job_dirs, relative_storage_path, resolve_stored_path


def utcnow() -> datetime:
    """Current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def create_job(
    db: Session,
    *,
    job_type: str,
    params: dict[str, Any],
    platform: str | None = None,
    source_url: str | None = None,
    client_id: str | None = None,
) -> Job:
    """Insert a queued job row."""
    settings = get_settings()
    job = Job(
        id=str(uuid.uuid4()),
        type=job_type,
        status="queued",
        stage="queued",
        progress=0,
        params=params,
        platform=platform,
        source_url=source_url,
        client_id=client_id,
        expires_at=utcnow() + timedelta(minutes=settings.file_ttl_minutes),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job_or_404(db: Session, job_id: str) -> Job:
    """Load a job or raise JOB_NOT_FOUND / JOB_EXPIRED."""
    job = db.get(Job, job_id)
    if job is None:
        raise AppError("JOB_NOT_FOUND", "Job not found.", status_code=404)
    if job.status == "expired":
        raise AppError("JOB_EXPIRED", "This job has expired.", status_code=410)
    return job


def update_job_progress(
    db: Session,
    job_id: str,
    *,
    progress: int | None = None,
    stage: str | None = None,
    status: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update job progress fields (throttling is caller's responsibility)."""
    job = db.get(Job, job_id)
    if job is None:
        return
    if progress is not None:
        job.progress = max(0, min(100, int(progress)))
    if stage is not None:
        job.stage = stage
    if status is not None:
        job.status = status
        if status == "processing" and job.started_at is None:
            job.started_at = utcnow()
        if status in {"completed", "failed", "cancelled", "expired"}:
            job.finished_at = utcnow()
    if error_code is not None:
        job.error_code = error_code
    if error_message is not None:
        job.error_message = error_message
    db.commit()


def add_job_file(
    db: Session,
    *,
    job_id: str,
    role: str,
    absolute_path: Path,
    original_name: str,
    part_index: int | None = None,
    mime_type: str | None = None,
    duration_seconds: float | None = None,
    width: int | None = None,
    height: int | None = None,
    codec_video: str | None = None,
    codec_audio: str | None = None,
) -> JobFile:
    """Register a job file row for a path on disk."""
    size = absolute_path.stat().st_size if absolute_path.exists() else 0
    row = JobFile(
        id=str(uuid.uuid4()),
        job_id=job_id,
        role=role,
        part_index=part_index,
        original_name=original_name,
        stored_path=relative_storage_path(absolute_path),
        mime_type=mime_type,
        size_bytes=size,
        duration_seconds=Decimal(str(round(duration_seconds, 3))) if duration_seconds is not None else None,
        width=width,
        height=height,
        codec_video=codec_video,
        codec_audio=codec_audio,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def mark_stale_processing_jobs(db: Session) -> int:
    """On startup, mark leftover processing jobs as failed."""
    jobs = db.scalars(select(Job).where(Job.status == "processing")).all()
    count = 0
    for job in jobs:
        job.status = "failed"
        job.error_code = "INTERNAL_ERROR"
        job.error_message = "Server restarted while job was processing."
        job.finished_at = utcnow()
        count += 1
    if count:
        db.commit()
    return count


def expire_jobs(db: Session) -> int:
    """Expire jobs past their TTL and delete files."""
    now = utcnow()
    jobs = db.scalars(
        select(Job).where(
            Job.expires_at < now,
            Job.status.notin_(["expired", "cancelled"]),
        )
    ).all()
    count = 0
    for job in jobs:
        delete_job_dirs(job.id)
        job.status = "expired"
        job.finished_at = now
        count += 1
    if count:
        db.commit()
    return count


def job_to_response(job: Job) -> JobStatusResponse:
    """Serialize a Job ORM object to the API response schema."""
    outputs: list[JobOutputOut] = []
    for f in sorted(
        [x for x in job.files if x.role == "output"],
        key=lambda x: (x.part_index is None, x.part_index or 0),
    ):
        outputs.append(
            JobOutputOut(
                file_id=f.id,
                name=f.original_name,
                part_index=f.part_index,
                duration_seconds=float(f.duration_seconds) if f.duration_seconds is not None else None,
                size_bytes=int(f.size_bytes),
                download_url=f"/api/files/{f.id}/download",
            )
        )

    zip_url = None
    if job.status == "completed" and outputs:
        zip_url = f"/api/jobs/{job.id}/zip"

    error = None
    if job.status == "failed":
        error = job.error_message or job.error_code

    return JobStatusResponse(
        job_id=job.id,
        type=job.type,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        error=error,
        created_at=job.created_at,
        expires_at=job.expires_at,
        outputs=outputs,
        zip_url=zip_url,
    )


def get_file_or_404(db: Session, file_id: str) -> tuple[JobFile, Path]:
    """Load a job file and resolve its path."""
    row = db.get(JobFile, file_id)
    if row is None:
        raise AppError("JOB_NOT_FOUND", "File not found.", status_code=404)
    job = db.get(Job, row.job_id)
    if job is None or job.status == "expired":
        raise AppError("JOB_EXPIRED", "This file has expired.", status_code=410)
    path = resolve_stored_path(row.stored_path)
    if not path.is_file():
        raise AppError("JOB_NOT_FOUND", "File not found on disk.", status_code=404)
    return row, path
