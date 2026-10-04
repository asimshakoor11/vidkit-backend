"""Streamed multipart upload helpers for tool endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import sanitize_filename, validate_upload_extension
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
