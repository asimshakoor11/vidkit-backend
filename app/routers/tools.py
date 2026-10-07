"""POST /api/tools/* — Markdown convert and URL shortener."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.core.security import validate_public_http_url
from app.models.short_url import ShortUrl
from app.routers.common import client_id
from app.schemas.video import JobCreatedResponse
from app.services.job_service import add_job_file, create_job
from app.services.storage import job_upload_dir
from app.services.tools.markdown import TARGETS
from app.services.upload import ImageUpload, save_markdown_upload
from app.workers import tasks as tool_tasks
from app.workers.runner import runner

router = APIRouter(tags=["tools"])
settings = get_settings()

MAX_MD_CHARS = 2 * 1024 * 1024


class ShortenRequest(BaseModel):
    url: str = Field(..., min_length=4, max_length=2048)


class ShortenResponse(BaseModel):
    code: str
    short_url: str
    expires_at: datetime


def _register_input(db: Session, job_id: str, uploaded: ImageUpload) -> None:
    add_job_file(
        db,
        job_id=job_id,
        role="input",
        absolute_path=uploaded.path,
        original_name=uploaded.original_name,
        mime_type=uploaded.content_type,
    )


async def _save_markdown_source(
    job_id: str,
    *,
    content: str | None,
    file: UploadFile | None,
) -> ImageUpload:
    if file is not None and (file.filename or "").strip():
        return await save_markdown_upload(file, job_id)

    text = (content or "").strip()
    if not text:
        raise AppError("UNSUPPORTED_FORMAT", "Provide Markdown content or upload a file.")
    if len(text) > MAX_MD_CHARS:
        raise AppError("FILE_TOO_LARGE", "Markdown content is too large.")
    dest = job_upload_dir(job_id) / "input.md"
    dest.write_text(text, encoding="utf-8")
    return ImageUpload(
        path=dest,
        original_name="input.md",
        content_type="text/markdown",
    )


@router.post("/api/tools/markdown", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def markdown_endpoint(
    request: Request,
    target: str = Form("html"),
    content: str = Form(""),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    target = (target or "html").lower().strip()
    if target not in TARGETS:
        raise AppError("UNSUPPORTED_FORMAT", "Target must be html or pdf.")

    job = create_job(
        db,
        job_type="md_convert",
        params={"target": target},
        client_id=client_id(request),
    )
    uploaded = await _save_markdown_source(job.id, content=content, file=file)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await tool_tasks.run_md_convert_job(job.id, uploaded.path, target)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


def _make_code(db: Session) -> str:
    for _ in range(12):
        code = secrets.token_urlsafe(6)[:8]
        exists = db.query(ShortUrl).filter(ShortUrl.code == code).first()
        if not exists:
            return code
    raise AppError("INTERNAL_ERROR", "Could not allocate a short code.")


@router.post("/api/tools/shorten", response_model=ShortenResponse)
@limiter.limit(settings.rate_limit_jobs)
async def shorten_endpoint(
    request: Request,
    body: ShortenRequest,
    db: Session = Depends(get_db),
) -> ShortenResponse:
    target = validate_public_http_url(body.url)
    code = _make_code(db)
    expires = datetime.now(timezone.utc) + timedelta(days=settings.short_url_ttl_days)
    row = ShortUrl(
        code=code,
        target_url=target,
        hits=0,
        client_id=client_id(request),
        expires_at=expires,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    base = settings.public_base_url.rstrip("/")
    return ShortenResponse(
        code=code,
        short_url=f"{base}/r/{code}",
        expires_at=row.expires_at,
    )


@router.get("/r/{code}")
async def redirect_short_url(code: str, db: Session = Depends(get_db)) -> RedirectResponse:
    row = db.query(ShortUrl).filter(ShortUrl.code == code).first()
    now = datetime.now(timezone.utc)
    if row is None:
        raise AppError("JOB_NOT_FOUND", "Short link not found.", status_code=404)
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise AppError("JOB_EXPIRED", "This short link has expired.", status_code=404)
    row.hits = int(row.hits or 0) + 1
    db.commit()
    return RedirectResponse(url=row.target_url, status_code=302)
