"""POST /api/pdf/* — PDF and document tool endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.routers.common import client_id
from app.schemas import pdf as pdf_schema
from app.schemas.video import JobCreatedResponse
from app.services.job_service import add_job_file, create_job
from app.services.upload import (
    save_doc_upload,
    save_image_upload,
    save_pdf_upload,
    save_pdf_uploads,
)
from app.workers import tasks as pdf_tasks
from app.workers.runner import runner

router = APIRouter(prefix="/api/pdf", tags=["pdf"])
settings = get_settings()


def _register_input(db: Session, job_id: str, uploaded) -> None:
    add_job_file(
        db,
        job_id=job_id,
        role="input",
        absolute_path=uploaded.path,
        original_name=uploaded.original_name,
        mime_type=uploaded.content_type,
        width=getattr(uploaded, "width", None),
        height=getattr(uploaded, "height", None),
    )


@router.post("/merge", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def merge_endpoint(
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if len(files) < 2:
        raise AppError("UNSUPPORTED_FORMAT", "Upload at least two PDF files to merge.")
    job = create_job(db, job_type="pdf_merge", params={"count": len(files)}, client_id=client_id(request))
    uploaded = await save_pdf_uploads(files, job.id)
    for item in uploaded:
        _register_input(db, job.id, item)
    paths = [u.path for u in uploaded]

    async def _factory() -> None:
        await pdf_tasks.run_pdf_merge_job(job.id, paths)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/split", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def split_endpoint(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("each"),
    ranges: str = Form(""),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if mode not in pdf_schema.SPLIT_MODES:
        raise AppError("UNSUPPORTED_FORMAT", "Mode must be each or ranges.")
    params = {"mode": mode}
    if mode == "ranges":
        params["ranges"] = ranges
    job = create_job(db, job_type="pdf_split", params=params, client_id=client_id(request))
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_split_job(job.id, uploaded.path, mode, ranges or None)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/compress", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def compress_endpoint(
    request: Request,
    file: UploadFile = File(...),
    preset: str = Form("ebook"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if preset not in pdf_schema.COMPRESS_PRESETS:
        raise AppError("UNSUPPORTED_FORMAT", "Preset must be screen, ebook, or printer.")
    job = create_job(db, job_type="pdf_compress", params={"preset": preset}, client_id=client_id(request))
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_compress_job(job.id, uploaded.path, preset)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/to-word", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def to_word_endpoint(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    job = create_job(db, job_type="pdf_to_word", params={}, client_id=client_id(request))
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_to_word_job(job.id, uploaded.path)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/from-word", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def from_word_endpoint(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    job = create_job(db, job_type="pdf_from_word", params={}, client_id=client_id(request))
    uploaded = await save_doc_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_from_word_job(job.id, uploaded.path)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/to-excel", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def to_excel_endpoint(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    job = create_job(db, job_type="pdf_to_excel", params={}, client_id=client_id(request))
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_to_excel_job(job.id, uploaded.path)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/to-jpg", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def to_jpg_endpoint(
    request: Request,
    file: UploadFile = File(...),
    dpi: int = Form(150),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if dpi not in pdf_schema.JPG_DPIS:
        raise AppError("UNSUPPORTED_FORMAT", "DPI must be 72, 100, 150, 200, or 300.")
    job = create_job(db, job_type="pdf_to_jpg", params={"dpi": dpi}, client_id=client_id(request))
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_to_jpg_job(job.id, uploaded.path, dpi)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/from-jpg", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def from_jpg_endpoint(
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if not files:
        raise AppError("UNSUPPORTED_FORMAT", "Upload at least one image.")
    job = create_job(db, job_type="pdf_from_jpg", params={"count": len(files)}, client_id=client_id(request))
    uploaded_list = []
    for index, f in enumerate(files):
        item = await save_image_upload(f, job.id, filename_stem="input", index=index)
        _register_input(db, job.id, item)
        uploaded_list.append(item)
    paths = [u.path for u in uploaded_list]

    async def _factory() -> None:
        await pdf_tasks.run_pdf_from_jpg_job(job.id, paths)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/rotate", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def rotate_endpoint(
    request: Request,
    file: UploadFile = File(...),
    angle: str = Form("90"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if angle not in pdf_schema.ROTATE_ANGLES:
        raise AppError("UNSUPPORTED_FORMAT", "Angle must be 90, 180, or 270.")
    job = create_job(db, job_type="pdf_rotate", params={"angle": angle}, client_id=client_id(request))
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_rotate_job(job.id, uploaded.path, angle)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/unlock", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def unlock_endpoint(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    # Never persist the raw password in job params
    job = create_job(
        db,
        job_type="pdf_unlock",
        params={"has_password": True},
        client_id=client_id(request),
    )
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)
    pwd = password

    async def _factory() -> None:
        await pdf_tasks.run_pdf_unlock_job(job.id, uploaded.path, pwd)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/protect", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def protect_endpoint(
    request: Request,
    file: UploadFile = File(...),
    password: str = Form(...),
    owner_password: str = Form(""),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if not password or len(password) < 4:
        raise AppError("UNSUPPORTED_FORMAT", "Password must be at least 4 characters.")
    job = create_job(
        db,
        job_type="pdf_protect",
        params={"has_password": True},
        client_id=client_id(request),
    )
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)
    user_pwd = password
    owner_pwd = owner_password or None

    async def _factory() -> None:
        await pdf_tasks.run_pdf_protect_job(job.id, uploaded.path, user_pwd, owner_pwd)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/ocr", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def ocr_endpoint(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form("eng"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if lang not in pdf_schema.OCR_LANGS:
        raise AppError("UNSUPPORTED_FORMAT", "Unsupported OCR language.")
    job = create_job(db, job_type="pdf_ocr", params={"lang": lang}, client_id=client_id(request))
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_ocr_job(job.id, uploaded.path, lang)

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/esign", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def esign_endpoint(
    request: Request,
    file: UploadFile = File(...),
    signature: UploadFile = File(...),
    page: int = Form(1),
    position: str = Form("br"),
    scale: float = Form(0.2),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if position not in pdf_schema.ESIGN_POSITIONS:
        raise AppError("UNSUPPORTED_FORMAT", "Invalid signature position.")
    if page < 1:
        raise AppError("UNSUPPORTED_FORMAT", "Page must be >= 1.")
    job = create_job(
        db,
        job_type="pdf_esign",
        params={"page": page, "position": position, "scale": scale},
        client_id=client_id(request),
    )
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)
    sig = await save_image_upload(signature, job.id, filename_stem="signature", index=1)
    _register_input(db, job.id, sig)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_esign_job(
            job.id, uploaded.path, sig.path, page=page, position=position, scale=scale
        )

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/watermark", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def watermark_endpoint(
    request: Request,
    file: UploadFile = File(...),
    text: str = Form(...),
    opacity: float = Form(0.3),
    angle: int = Form(45),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if not text.strip():
        raise AppError("UNSUPPORTED_FORMAT", "Watermark text is required.")
    job = create_job(
        db,
        job_type="pdf_watermark",
        params={"text": text[:120], "opacity": opacity, "angle": angle},
        client_id=client_id(request),
    )
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_watermark_job(
            job.id, uploaded.path, text=text, opacity=opacity, angle=angle
        )

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")


@router.post("/page-numbers", response_model=JobCreatedResponse, status_code=202)
@limiter.limit(settings.rate_limit_jobs)
async def page_numbers_endpoint(
    request: Request,
    file: UploadFile = File(...),
    position: str = Form("bc"),
    start: int = Form(1),
    format_str: str = Form("{n}"),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    if position not in pdf_schema.PAGE_NUM_POSITIONS:
        raise AppError("UNSUPPORTED_FORMAT", "Invalid page number position.")
    job = create_job(
        db,
        job_type="pdf_pagenum",
        params={"position": position, "start": start, "format": format_str},
        client_id=client_id(request),
    )
    uploaded = await save_pdf_upload(file, job.id)
    _register_input(db, job.id, uploaded)

    async def _factory() -> None:
        await pdf_tasks.run_pdf_pagenum_job(
            job.id, uploaded.path, position=position, start=start, format_str=format_str
        )

    await runner.submit(job.id, _factory)
    return JobCreatedResponse(job_id=job.id, status="queued")
