"""POST /api/audio/* — audio tool endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.routers.common import client_id
from app.schemas import audio as audio_schema
from app.schemas.video import JobCreatedResponse
from app.services.job_service import add_job_file, create_job
from app.services.upload import save_audio_upload, save_audio_uploads
from app.workers import tasks as audio_tasks
from app.workers.runner import runner

router = APIRouter(prefix="/api/audio", tags=["audio"])
settings = get_settings()


def _register_input(db: Session, job_id: str, uploaded) -> None:
    add_job_file(
        db,
        job_id=job_id,
        role="input",
        absolute_path=uploaded.path,
        original_name=uploaded.original_name,
        mime_type=uploaded.content_type,
        duration_seconds=getattr(getattr(uploaded, "info", None), "duration", None),
        codec_audio=getattr(getattr(uploaded, "info", None), "codec_audio", None),
    )


@router.post("/convert", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def convert_endpoint(
    request: Request,
    file: UploadFile = File(...),
    fmt: str = Form("mp3"),
    bitrate: str = Form("192k"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    fmt = fmt.lower()
    if fmt not in audio_schema.CONVERT_FMTS:
        raise AppError("UNSUPPORTED_FORMAT", "Format must be mp3, wav, aac, or flac.")
    if fmt in {"mp3", "aac"} and bitrate not in audio_schema.LOSSY_BITRATES:
        raise AppError("UNSUPPORTED_FORMAT", "Bitrate must be 128k, 192k, 256k, or 320k.")
    job = create_job(
        db,
        job_type="audio_convert",
        params={"fmt": fmt, "bitrate": bitrate},
        client_id=client_id(request),
    )
    uploaded = await save_audio_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await audio_tasks.run_audio_convert_job(job.id, uploaded.path, fmt, bitrate)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/compress", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def compress_endpoint(
    request: Request,
    file: UploadFile = File(...),
    preset: str = Form("balanced"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if preset not in audio_schema.COMPRESS_PRESETS:
        raise AppError("UNSUPPORTED_FORMAT", "Preset must be high, balanced, or small.")
    job = create_job(
        db, job_type="audio_compress", params={"preset": preset}, client_id=client_id(request)
    )
    uploaded = await save_audio_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await audio_tasks.run_audio_compress_job(job.id, uploaded.path, preset)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/trim", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def trim_endpoint(
    request: Request,
    file: UploadFile = File(...),
    start: float = Form(...),
    end: float = Form(...),
    mode: str = Form("fast"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if mode not in audio_schema.TRIM_MODES:
        raise AppError("UNSUPPORTED_FORMAT", "Mode must be fast or precise.")
    job = create_job(
        db,
        job_type="audio_trim",
        params={"start": start, "end": end, "mode": mode},
        client_id=client_id(request),
    )
    uploaded = await save_audio_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await audio_tasks.run_audio_trim_job(job.id, uploaded.path, start, end, mode)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/merge", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def merge_endpoint(
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if len(files) < 2:
        raise AppError("UNSUPPORTED_FORMAT", "Upload at least two audio files to merge.")
    job = create_job(
        db, job_type="audio_merge", params={"count": len(files)}, client_id=client_id(request)
    )
    uploaded = await save_audio_uploads(files, job.id)
    for item in uploaded:
        _register_input(db, job.id, item)
    paths = [u.path for u in uploaded]

    async def _factory() -> None:
        await audio_tasks.run_audio_merge_job(job.id, paths)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/denoise", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def denoise_endpoint(
    request: Request,
    file: UploadFile = File(...),
    preset: str = Form("medium"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if preset not in audio_schema.DENOISE_PRESETS:
        raise AppError("UNSUPPORTED_FORMAT", "Preset must be light, medium, or strong.")
    job = create_job(
        db, job_type="audio_denoise", params={"preset": preset}, client_id=client_id(request)
    )
    uploaded = await save_audio_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await audio_tasks.run_audio_denoise_job(job.id, uploaded.path, preset)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/separate", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def separate_endpoint(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    job = create_job(db, job_type="audio_separate", params={}, client_id=client_id(request))
    uploaded = await save_audio_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await audio_tasks.run_audio_separate_job(job.id, uploaded.path)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")
