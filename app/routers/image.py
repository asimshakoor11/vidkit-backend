"""POST /api/image/* — image tool endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.routers.common import client_id
from app.schemas import image as img_schema
from app.schemas.video import JobCreatedResponse
from app.services.job_service import add_job_file, create_job
from app.services.upload import save_image_upload
from app.workers.runner import runner
from app.workers import tasks as image_tasks

router = APIRouter(prefix="/api/image", tags=["image"])
settings = get_settings()


def _register_input(db: Session, job_id: str, uploaded) -> None:
    add_job_file(
        db,
        job_id=job_id,
        role="input",
        absolute_path=uploaded.path,
        original_name=uploaded.original_name,
        mime_type=uploaded.content_type,
        width=uploaded.width,
        height=uploaded.height,
    )


@router.post("/compress", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def compress_endpoint(
    request: Request,
    file: UploadFile = File(...),
    preset: str = Form("balanced"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if preset not in img_schema.COMPRESS_PRESETS:
        raise AppError("UNSUPPORTED_FORMAT", "Preset must be high, balanced, or small.")
    job = create_job(db, job_type="img_compress", params={"preset": preset}, client_id=client_id(request))
    uploaded = await save_image_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await image_tasks.run_img_compress_job(job.id, uploaded.path, preset)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/target-size", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def target_size_endpoint(
    request: Request,
    file: UploadFile = File(...),
    kb: int = Form(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if kb < 1 or kb > 50_000:
        raise AppError("UNSUPPORTED_FORMAT", "Target size must be between 1 and 50000 KB.")
    job = create_job(db, job_type="img_target", params={"kb": kb}, client_id=client_id(request))
    uploaded = await save_image_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await image_tasks.run_img_target_job(job.id, uploaded.path, kb)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/convert", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def convert_endpoint(
    request: Request,
    file: UploadFile = File(...),
    fmt: str = Form(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    key = fmt.lower()
    if key == "jpeg":
        key = "jpg"
    if key not in img_schema.CONVERT_FMTS and key != "jpg":
        raise AppError("UNSUPPORTED_FORMAT", "Format must be jpg, png, webp, or avif.")
    job = create_job(db, job_type="img_convert", params={"fmt": key}, client_id=client_id(request))
    uploaded = await save_image_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await image_tasks.run_img_convert_job(job.id, uploaded.path, key)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/resize", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def resize_endpoint(
    request: Request,
    file: UploadFile = File(...),
    w: int | None = Form(None),
    h: int | None = Form(None),
    mode: str = Form("fit"),
    crop_x: int | None = Form(None),
    crop_y: int | None = Form(None),
    crop_w: int | None = Form(None),
    crop_h: int | None = Form(None),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if mode not in img_schema.RESIZE_MODES:
        raise AppError("UNSUPPORTED_FORMAT", "Mode must be fit, fill, or exact.")
    has_crop = any(v is not None for v in (crop_x, crop_y, crop_w, crop_h))
    if has_crop and None in (crop_x, crop_y, crop_w, crop_h):
        raise AppError("INVALID_RANGE", "Provide all crop fields: crop_x, crop_y, crop_w, crop_h.")
    if not has_crop and not w and not h:
        raise AppError("UNSUPPORTED_FORMAT", "Provide width/height or a crop box.")

    params = {
        "w": w,
        "h": h,
        "mode": mode,
        "crop_x": crop_x,
        "crop_y": crop_y,
        "crop_w": crop_w,
        "crop_h": crop_h,
    }
    job = create_job(db, job_type="img_resize", params=params, client_id=client_id(request))
    uploaded = await save_image_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await image_tasks.run_img_resize_job(
            job.id,
            uploaded.path,
            width=w,
            height=h,
            mode=mode,
            crop_x=crop_x,
            crop_y=crop_y,
            crop_w=crop_w,
            crop_h=crop_h,
        )

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/pdf", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def pdf_endpoint(
    request: Request,
    file: UploadFile = File(...),
    direction: str = Form(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if direction not in img_schema.PDF_DIRECTIONS:
        raise AppError("UNSUPPORTED_FORMAT", "Direction must be to_pdf or from_pdf.")
    job = create_job(
        db, job_type="img_pdf", params={"direction": direction}, client_id=client_id(request)
    )
    uploaded = await save_image_upload(file, job.id, allow_pdf=True)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await image_tasks.run_img_pdf_job(job.id, uploaded.path, direction)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/watermark", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def watermark_endpoint(
    request: Request,
    file: UploadFile = File(...),
    text: str = Form(""),
    position: str = Form("br"),
    opacity: float = Form(0.4),
    scale: float = Form(0.2),
    mark: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if position not in img_schema.WATERMARK_POSITIONS:
        raise AppError("UNSUPPORTED_FORMAT", "Invalid watermark position.")
    if not text.strip() and mark is None:
        raise AppError("UNSUPPORTED_FORMAT", "Provide watermark text or an overlay image.")

    job = create_job(
        db,
        job_type="img_watermark",
        params={"text": text, "position": position, "opacity": opacity, "scale": scale},
        client_id=client_id(request),
    )
    uploaded = await save_image_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    mark_path: Path | None = None
    if mark is not None and mark.filename:
        mark_up = await save_image_upload(mark, job.id, filename_stem="mark", index=1)
        add_job_file(
            db,
            job_id=job.id,
            role="input",
            absolute_path=mark_up.path,
            original_name=mark_up.original_name,
            mime_type=mark_up.content_type,
            width=mark_up.width,
            height=mark_up.height,
            part_index=2,
        )
        mark_path = mark_up.path

    async def _factory() -> None:
        await image_tasks.run_img_watermark_job(
            job.id,
            uploaded.path,
            text=text.strip() or None,
            mark_path=mark_path,
            position=position,
            opacity=opacity,
            scale=scale,
        )

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/meme", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def meme_endpoint(
    request: Request,
    file: UploadFile = File(...),
    top: str = Form(""),
    bottom: str = Form(""),
    font_size: int | None = Form(None),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if not top.strip() and not bottom.strip():
        raise AppError("UNSUPPORTED_FORMAT", "Enter top and/or bottom meme text.")
    job = create_job(
        db,
        job_type="img_meme",
        params={"top": top, "bottom": bottom, "font_size": font_size},
        client_id=client_id(request),
    )
    uploaded = await save_image_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await image_tasks.run_img_meme_job(
            job.id, uploaded.path, top=top, bottom=bottom, font_size=font_size
        )

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/exif", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def exif_endpoint(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("strip"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if mode not in img_schema.EXIF_MODES:
        raise AppError("UNSUPPORTED_FORMAT", "Mode must be view or strip.")
    job = create_job(db, job_type="img_exif", params={"mode": mode}, client_id=client_id(request))
    uploaded = await save_image_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await image_tasks.run_img_exif_job(job.id, uploaded.path, mode)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/favicon", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def favicon_endpoint(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    job = create_job(db, job_type="img_favicon", params={}, client_id=client_id(request))
    uploaded = await save_image_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await image_tasks.run_img_favicon_job(job.id, uploaded.path)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")
