"""Streamed multipart upload helpers for tool endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    sanitize_filename,
    validate_audio_extension,
    validate_doc_extension,
    validate_image_extension,
    validate_pdf_extension,
    validate_upload_extension,
)
from app.services.ffprobe import ProbeInfo, probe
from app.services.storage import job_upload_dir

CHUNK_SIZE = 1024 * 1024  # 1 MiB


@dataclass
class UploadedFile:
    """Saved upload on disk with probe metadata."""

    path: Path
    original_name: str
    info: ProbeInfo
    content_type: str | None
    index: int = 0


@dataclass
class ImageUpload:
    """Saved image/PDF upload with basic dimensions."""

    path: Path
    original_name: str
    content_type: str | None
    width: int | None = None
    height: int | None = None
    index: int = 0


async def save_upload(
    file: UploadFile,
    job_id: str,
    *,
    require_video: bool = True,
    filename_stem: str = "input",
    index: int = 0,
) -> UploadedFile:
    """Stream one upload into the job upload dir; enforce size and duration limits."""
    settings = get_settings()
    original_name = sanitize_filename(file.filename or "video.mp4")
    ext = validate_upload_extension(original_name)

    upload_dir = job_upload_dir(job_id)
    dest = upload_dir / f"{filename_stem}{ext}" if index == 0 else upload_dir / f"{filename_stem}_{index:02d}{ext}"

    total = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise AppError(
                        "FILE_TOO_LARGE",
                        f"File exceeds the {settings.max_upload_mb} MB upload limit.",
                    )
                out.write(chunk)
    finally:
        await file.close()

    info = probe(dest)
    if require_video and info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not read this video file.")
    if info.duration > settings.max_video_duration_seconds:
        raise AppError(
            "DURATION_LIMIT",
            f"Video exceeds the {settings.max_video_duration_min} minute limit.",
        )

    return UploadedFile(
        path=dest,
        original_name=original_name,
        info=info,
        content_type=file.content_type,
        index=index,
    )


async def save_uploads(
    files: list[UploadFile],
    job_id: str,
    *,
    max_files: int = 10,
) -> list[UploadedFile]:
    """Save multiple uploads; enforces per-file size and max file count."""
    if not files:
        raise AppError("UNSUPPORTED_FORMAT", "Please upload at least one video file.")
    if len(files) > max_files:
        raise AppError("FILE_TOO_LARGE", f"You can upload at most {max_files} files.")

    settings = get_settings()
    saved: list[UploadedFile] = []
    total_bytes = 0
    for index, file in enumerate(files):
        item = await save_upload(file, job_id, filename_stem="input", index=index)
        total_bytes += item.path.stat().st_size
        if total_bytes > settings.max_upload_bytes:
            raise AppError(
                "FILE_TOO_LARGE",
                f"Total upload exceeds the {settings.max_upload_mb} MB limit.",
            )
        saved.append(item)
    return saved


async def save_image_upload(
    file: UploadFile,
    job_id: str,
    *,
    allow_pdf: bool = False,
    filename_stem: str = "input",
    index: int = 0,
    validate_open: bool = True,
) -> ImageUpload:
    """Stream an image (or PDF) upload; no ffprobe / duration checks."""
    settings = get_settings()
    original_name = sanitize_filename(file.filename or "image.png")
    ext = validate_image_extension(original_name, allow_pdf=allow_pdf)

    upload_dir = job_upload_dir(job_id)
    dest = (
        upload_dir / f"{filename_stem}{ext}"
        if index == 0
        else upload_dir / f"{filename_stem}_{index:02d}{ext}"
    )

    total = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise AppError(
                        "FILE_TOO_LARGE",
                        f"File exceeds the {settings.max_upload_mb} MB upload limit.",
                    )
                out.write(chunk)
    finally:
        await file.close()

    width = height = None
    if validate_open and ext != ".pdf":
        from app.services.image.io import open_image

        img = open_image(dest)
        width, height = img.width, img.height
        img.close()
    elif ext == ".pdf" and validate_open:
        # Light existence check — detailed open happens in the PDF service
        if dest.stat().st_size < 5:
            raise AppError("UNSUPPORTED_FORMAT", "Could not read this PDF file.")

    return ImageUpload(
        path=dest,
        original_name=original_name,
        content_type=file.content_type,
        width=width,
        height=height,
        index=index,
    )


async def _stream_upload(
    file: UploadFile,
    dest: Path,
) -> int:
    """Write upload chunks to dest; return byte count. Closes the UploadFile."""
    settings = get_settings()
    total = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise AppError(
                        "FILE_TOO_LARGE",
                        f"File exceeds the {settings.max_upload_mb} MB upload limit.",
                    )
                out.write(chunk)
    finally:
        await file.close()
    return total


async def save_pdf_upload(
    file: UploadFile,
    job_id: str,
    *,
    filename_stem: str = "input",
    index: int = 0,
) -> ImageUpload:
    """Stream a PDF upload into the job upload dir."""
    original_name = sanitize_filename(file.filename or "document.pdf")
    ext = validate_pdf_extension(original_name)
    upload_dir = job_upload_dir(job_id)
    dest = (
        upload_dir / f"{filename_stem}{ext}"
        if index == 0
        else upload_dir / f"{filename_stem}_{index:02d}{ext}"
    )
    await _stream_upload(file, dest)
    if dest.stat().st_size < 5:
        raise AppError("UNSUPPORTED_FORMAT", "Could not read this PDF file.")
    return ImageUpload(
        path=dest,
        original_name=original_name,
        content_type=file.content_type or "application/pdf",
        index=index,
    )


async def save_pdf_uploads(
    files: list[UploadFile],
    job_id: str,
    *,
    max_files: int = 20,
) -> list[ImageUpload]:
    """Save multiple PDF uploads; enforces max file count and total size."""
    if not files:
        raise AppError("UNSUPPORTED_FORMAT", "Please upload at least one PDF file.")
    if len(files) > max_files:
        raise AppError("FILE_TOO_LARGE", f"You can upload at most {max_files} files.")

    settings = get_settings()
    saved: list[ImageUpload] = []
    total_bytes = 0
    for index, file in enumerate(files):
        item = await save_pdf_upload(file, job_id, filename_stem="input", index=index)
        total_bytes += item.path.stat().st_size
        if total_bytes > settings.max_upload_bytes:
            raise AppError(
                "FILE_TOO_LARGE",
                f"Total upload exceeds the {settings.max_upload_mb} MB limit.",
            )
        saved.append(item)
    return saved


async def save_doc_upload(
    file: UploadFile,
    job_id: str,
    *,
    filename_stem: str = "input",
    index: int = 0,
) -> ImageUpload:
    """Stream a DOCX upload into the job upload dir."""
    original_name = sanitize_filename(file.filename or "document.docx")
    ext = validate_doc_extension(original_name)
    upload_dir = job_upload_dir(job_id)
    dest = (
        upload_dir / f"{filename_stem}{ext}"
        if index == 0
        else upload_dir / f"{filename_stem}_{index:02d}{ext}"
    )
    await _stream_upload(file, dest)
    if dest.stat().st_size < 5:
        raise AppError("UNSUPPORTED_FORMAT", "Could not read this Word document.")
    return ImageUpload(
        path=dest,
        original_name=original_name,
        content_type=file.content_type
        or "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        index=index,
    )


@dataclass
class AudioUpload:
    """Saved audio upload with probe duration."""

    path: Path
    original_name: str
    info: ProbeInfo
    content_type: str | None
    index: int = 0


async def save_audio_upload(
    file: UploadFile,
    job_id: str,
    *,
    filename_stem: str = "input",
    index: int = 0,
) -> AudioUpload:
    """Stream an audio upload; probe duration (no video required)."""
    settings = get_settings()
    original_name = sanitize_filename(file.filename or "audio.mp3")
    ext = validate_audio_extension(original_name)
    upload_dir = job_upload_dir(job_id)
    dest = (
        upload_dir / f"{filename_stem}{ext}"
        if index == 0
        else upload_dir / f"{filename_stem}_{index:02d}{ext}"
    )
    await _stream_upload(file, dest)

    info = probe(dest)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not read this audio file.")
    if info.duration > settings.max_video_duration_seconds:
        raise AppError(
            "DURATION_LIMIT",
            f"Audio exceeds the {settings.max_video_duration_min} minute limit.",
        )

    return AudioUpload(
        path=dest,
        original_name=original_name,
        info=info,
        content_type=file.content_type,
        index=index,
    )


async def save_audio_uploads(
    files: list[UploadFile],
    job_id: str,
    *,
    max_files: int = 20,
) -> list[AudioUpload]:
    """Save multiple audio uploads."""
    if not files:
        raise AppError("UNSUPPORTED_FORMAT", "Please upload at least one audio file.")
    if len(files) > max_files:
        raise AppError("FILE_TOO_LARGE", f"You can upload at most {max_files} files.")

    settings = get_settings()
    saved: list[AudioUpload] = []
    total_bytes = 0
    for index, file in enumerate(files):
        item = await save_audio_upload(file, job_id, filename_stem="input", index=index)
        total_bytes += item.path.stat().st_size
        if total_bytes > settings.max_upload_bytes:
            raise AppError(
                "FILE_TOO_LARGE",
                f"Total upload exceeds the {settings.max_upload_mb} MB limit.",
            )
        saved.append(item)
    return saved
