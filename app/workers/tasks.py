"""Job execution callbacks used by routers."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.config import get_settings
from collections.abc import Callable

from app.services import compress as compress_service
from app.services import convert as convert_service
from app.services import downloader as downloader_service
from app.services import extract as extract_service
from app.services import gif as gif_service
from app.services import merge as merge_service
from app.services import resize as resize_service
from app.services import rotate as rotate_service
from app.services import trim as trim_service
from app.services.ffmpeg import FfmpegProcess
from app.services.ffprobe import probe
from app.services.image import compress as img_compress
from app.services.image import convert as img_convert
from app.services.image import exif as img_exif
from app.services.image import favicon as img_favicon
from app.services.image import meme as img_meme
from app.services.image import pdf as img_pdf
from app.services.image import resize as img_resize
from app.services.image import watermark as img_watermark
from app.services.image.io import mime_for_ext
from app.services.job_service import add_job_file, update_job_progress
from app.services.pdf import annotate as pdf_annotate
from app.services.pdf import compress as pdf_compress
from app.services.pdf import convert as pdf_convert
from app.services.pdf import merge as pdf_merge
from app.services.pdf import ocr as pdf_ocr
from app.services.pdf import secure as pdf_secure
from app.services.pdf import split as pdf_split
from app.services.audio import compress as aud_compress
from app.services.audio import convert as aud_convert
from app.services.audio import denoise as aud_denoise
from app.services.audio import merge as aud_merge
from app.services.audio import separate as aud_separate
from app.services.audio import trim as aud_trim
from app.services.splitter import SplitProcess, split_video
from app.services.storage import job_output_dir, job_upload_dir
from app.services.tools import markdown as md_convert
from app.workers.runner import runner

logger = get_logger(__name__)

# Active ffmpeg trackers for cancel support
_ffmpeg_trackers: dict[str, FfmpegProcess] = {}
_split_trackers = _ffmpeg_trackers  # alias


def get_split_tracker(job_id: str) -> FfmpegProcess | None:
    return _ffmpeg_trackers.get(job_id)


def _mime_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    mapped = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".aac": "audio/aac",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".html": "text/html",
        ".htm": "text/html",
    }.get(ext)
    if mapped:
        return mapped
    return mime_for_ext(ext)


async def _run_single_output_job(
    job_id: str,
    work: Callable[[FfmpegProcess, Callable[[float, str], None]], Path],
) -> None:
    """Shared orchestrator for single-file FFmpeg tools."""
    db = SessionLocal()
    tracker = FfmpegProcess()
    _ffmpeg_trackers[job_id] = tracker
    runner.register_cancel_hook(job_id, tracker.cancel)
    last_write = 0.0

    def on_progress(percent: float, stage: str) -> None:
        nonlocal last_write
        now = time.monotonic()
        if now - last_write < 1.0 and percent < 99:
            return
        last_write = now
        update_job_progress(
            db,
            job_id,
            progress=int(percent),
            stage=stage,
            status="processing",
        )

    try:
        update_job_progress(db, job_id, status="processing", stage="processing", progress=1)
        path = await asyncio.to_thread(work, tracker, on_progress)

        if runner.is_cancelled(job_id) or tracker.cancelled:
            update_job_progress(db, job_id, status="cancelled", stage="cancelled", progress=0)
            return

        duration = width = height = None
        codec_v = codec_a = None
        try:
            meta = await asyncio.to_thread(probe, path)
            duration = meta.duration if meta.duration > 0 else None
            width = meta.width
            height = meta.height
            codec_v = meta.codec_video
            codec_a = meta.codec_audio
        except Exception:  # noqa: BLE001
            logger.warning("output_probe_skipped", path=str(path))

        add_job_file(
            db,
            job_id=job_id,
            role="output",
            absolute_path=path,
            original_name=path.name,
            part_index=1,
            mime_type=_mime_for_path(path),
            duration_seconds=duration,
            width=width,
            height=height,
            codec_video=codec_v,
            codec_audio=codec_a,
        )
        update_job_progress(db, job_id, status="completed", stage="packaging", progress=100)
        logger.info("media_job_completed", job_id=job_id, path=str(path))
    except AppError as exc:
        status = "cancelled" if tracker.cancelled else "failed"
        update_job_progress(
            db,
            job_id,
            status=status,
            stage=status,
            error_code=exc.code if status == "failed" else None,
            error_message=exc.message if status == "failed" else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("media_job_failed", job_id=job_id)
        update_job_progress(
            db,
            job_id,
            status="failed",
            stage="failed",
            error_code="INTERNAL_ERROR",
            error_message=str(exc) or "Processing failed",
        )
    finally:
        _ffmpeg_trackers.pop(job_id, None)
        runner.clear_cancel_hook(job_id)
        db.close()


async def run_download_job(job_id: str, url: str, format_id: str) -> None:
    """Execute a download job in a worker thread + update DB progress."""
    db = SessionLocal()
    last_write = 0.0

    def on_progress(percent: float, stage: str) -> None:
        nonlocal last_write
        now = time.monotonic()
        if now - last_write < 1.0 and percent < 95:
            return
        last_write = now
        update_job_progress(
            db,
            job_id,
            progress=int(percent),
            stage=stage,
            status="processing",
        )

    try:
        update_job_progress(db, job_id, status="processing", stage="fetching", progress=1)
        out_dir = job_output_dir(job_id)

        path = await asyncio.to_thread(
            downloader_service.download_video,
            url,
            format_id,
            out_dir,
            on_progress,
        )

        if runner.is_cancelled(job_id):
            update_job_progress(
                db,
                job_id,
                status="cancelled",
                stage="cancelled",
                progress=0,
            )
            return

        add_job_file(
            db,
            job_id=job_id,
            role="output",
            absolute_path=path,
            original_name=path.name,
            part_index=1,
            mime_type="audio/mpeg" if path.suffix.lower() == ".mp3" else "video/mp4",
        )
        update_job_progress(db, job_id, status="completed", stage="packaging", progress=100)
        logger.info("download_job_completed", job_id=job_id, path=str(path))
    except AppError as exc:
        update_job_progress(
            db,
            job_id,
            status="failed",
            stage="failed",
            error_code=exc.code,
            error_message=exc.message,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("download_job_failed", job_id=job_id)
        update_job_progress(
            db,
            job_id,
            status="failed",
            stage="failed",
            error_code="INTERNAL_ERROR",
            error_message=str(exc) or "Download failed",
        )
    finally:
        db.close()


async def run_split_job(
    job_id: str,
    input_path: Path,
    chunk_seconds: int,
    mode: str,
) -> None:
    """Execute a split job."""
    db = SessionLocal()
    tracker = SplitProcess()
    _split_trackers[job_id] = tracker
    runner.register_cancel_hook(job_id, tracker.cancel)
    last_write = 0.0

    def on_progress(percent: float, stage: str) -> None:
        nonlocal last_write
        now = time.monotonic()
        if now - last_write < 1.0 and percent < 99:
            return
        last_write = now
        update_job_progress(
            db,
            job_id,
            progress=int(percent),
            stage=stage,
            status="processing",
        )

    try:
        update_job_progress(db, job_id, status="processing", stage="splitting", progress=1)
        info = await asyncio.to_thread(probe, input_path)
        out_dir = job_output_dir(job_id)

        parts = await asyncio.to_thread(
            split_video,
            input_path,
            out_dir,
            chunk_seconds,
            mode,
            info,
            on_progress,
            tracker,
        )

        if runner.is_cancelled(job_id) or tracker.cancelled:
            update_job_progress(db, job_id, status="cancelled", stage="cancelled", progress=0)
            return

        for index, part in enumerate(parts, start=1):
            part_info = await asyncio.to_thread(probe, part)
            add_job_file(
                db,
                job_id=job_id,
                role="output",
                absolute_path=part,
                original_name=part.name,
                part_index=index,
                mime_type="video/mp4",
                duration_seconds=part_info.duration,
                width=part_info.width,
                height=part_info.height,
                codec_video=part_info.codec_video,
                codec_audio=part_info.codec_audio,
            )

        update_job_progress(db, job_id, status="completed", stage="packaging", progress=100)
        logger.info("split_job_completed", job_id=job_id, parts=len(parts))
    except AppError as exc:
        status = "cancelled" if tracker.cancelled else "failed"
        update_job_progress(
            db,
            job_id,
            status=status,
            stage=status,
            error_code=exc.code if status == "failed" else None,
            error_message=exc.message if status == "failed" else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("split_job_failed", job_id=job_id)
        update_job_progress(
            db,
            job_id,
            status="failed",
            stage="failed",
            error_code="INTERNAL_ERROR",
            error_message=str(exc) or "Split failed",
        )
    finally:
        _ffmpeg_trackers.pop(job_id, None)
        runner.clear_cancel_hook(job_id)
        db.close()


async def run_download_split_job(
    job_id: str,
    url: str,
    format_id: str,
    chunk_seconds: int,
    mode: str,
) -> None:
    """Download a video from URL, then split it into parts."""
    db = SessionLocal()
    tracker = SplitProcess()
    _split_trackers[job_id] = tracker
    runner.register_cancel_hook(job_id, tracker.cancel)
    last_write = 0.0

    def on_download_progress(percent: float, stage: str) -> None:
        nonlocal last_write
        now = time.monotonic()
        if now - last_write < 1.0 and percent < 95:
            return
        last_write = now
        # Map download 0–100 → overall 0–55
        mapped = max(1, min(55, int(percent * 0.55)))
        update_job_progress(
            db,
            job_id,
            progress=mapped,
            stage=stage,
            status="processing",
        )

    def on_split_progress(percent: float, stage: str) -> None:
        nonlocal last_write
        now = time.monotonic()
        if now - last_write < 1.0 and percent < 99:
            return
        last_write = now
        # Map split 0–100 → overall 55–100
        mapped = 55 + int((percent / 100) * 45)
        update_job_progress(
            db,
            job_id,
            progress=min(99, mapped),
            stage=stage,
            status="processing",
        )

    try:
        update_job_progress(db, job_id, status="processing", stage="fetching", progress=1)
        upload_dir = job_upload_dir(job_id)

        path = await asyncio.to_thread(
            downloader_service.download_video,
            url,
            format_id,
            upload_dir,
            on_download_progress,
        )

        if runner.is_cancelled(job_id) or tracker.cancelled:
            update_job_progress(db, job_id, status="cancelled", stage="cancelled", progress=0)
            return

        info = await asyncio.to_thread(probe, path)
        if info.duration <= 0:
            raise AppError("UNSUPPORTED_FORMAT", "Could not read the downloaded video.")
        settings = get_settings()
        if info.duration > settings.max_video_duration_seconds:
            raise AppError(
                "DURATION_LIMIT",
                f"Video exceeds the {settings.max_video_duration_min} minute limit.",
            )
        if chunk_seconds >= info.duration:
            raise AppError(
                "INVALID_CHUNK_LENGTH",
                "Chunk length must be shorter than the video duration.",
            )

        add_job_file(
            db,
            job_id=job_id,
            role="input",
            absolute_path=path,
            original_name=path.name,
            mime_type="video/mp4",
            duration_seconds=info.duration,
            width=info.width,
            height=info.height,
            codec_video=info.codec_video,
            codec_audio=info.codec_audio,
        )

        update_job_progress(db, job_id, status="processing", stage="splitting", progress=55)
        out_dir = job_output_dir(job_id)

        parts = await asyncio.to_thread(
            split_video,
            path,
            out_dir,
            chunk_seconds,
            mode,
            info,
            on_split_progress,
            tracker,
        )

        if runner.is_cancelled(job_id) or tracker.cancelled:
            update_job_progress(db, job_id, status="cancelled", stage="cancelled", progress=0)
            return

        for index, part in enumerate(parts, start=1):
            part_info = await asyncio.to_thread(probe, part)
            add_job_file(
                db,
                job_id=job_id,
                role="output",
                absolute_path=part,
                original_name=part.name,
                part_index=index,
                mime_type="video/mp4",
                duration_seconds=part_info.duration,
                width=part_info.width,
                height=part_info.height,
                codec_video=part_info.codec_video,
                codec_audio=part_info.codec_audio,
            )

        update_job_progress(db, job_id, status="completed", stage="packaging", progress=100)
        logger.info("download_split_job_completed", job_id=job_id, parts=len(parts))
    except AppError as exc:
        status = "cancelled" if tracker.cancelled else "failed"
        update_job_progress(
            db,
            job_id,
            status=status,
            stage=status,
            error_code=exc.code if status == "failed" else None,
            error_message=exc.message if status == "failed" else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("download_split_job_failed", job_id=job_id)
        update_job_progress(
            db,
            job_id,
            status="failed",
            stage="failed",
            error_code="INTERNAL_ERROR",
            error_message=str(exc) or "Download and split failed",
        )
    finally:
        _ffmpeg_trackers.pop(job_id, None)
        runner.clear_cancel_hook(job_id)
        db.close()


async def run_compress_job(job_id: str, input_path: Path, preset: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return compress_service.compress_video(
            input_path, out_dir, preset, progress_callback=on_progress, tracker=tracker
        )

    await _run_single_output_job(job_id, work)


async def run_extract_job(job_id: str, input_path: Path, fmt: str, bitrate: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return extract_service.extract_audio(
            input_path,
            out_dir,
            fmt=fmt,
            bitrate=bitrate,
            progress_callback=on_progress,
            tracker=tracker,
        )

    await _run_single_output_job(job_id, work)


async def run_trim_job(
    job_id: str, input_path: Path, start: float, end: float, mode: str
) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return trim_service.trim_video(
            input_path,
            out_dir,
            start,
            end,
            mode=mode,
            progress_callback=on_progress,
            tracker=tracker,
        )

    await _run_single_output_job(job_id, work)


async def run_convert_job(job_id: str, input_path: Path, target: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return convert_service.convert_video(
            input_path, out_dir, target, progress_callback=on_progress, tracker=tracker
        )

    await _run_single_output_job(job_id, work)


async def run_merge_job(job_id: str, input_paths: list[Path]) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return merge_service.merge_videos(
            input_paths, out_dir, progress_callback=on_progress, tracker=tracker
        )

    await _run_single_output_job(job_id, work)


async def run_gif_job(
    job_id: str,
    input_path: Path,
    start: float,
    duration: float,
    width: int,
    fps: int,
) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return gif_service.make_gif(
            input_path,
            out_dir,
            start=start,
            duration=duration,
            width=width,
            fps=fps,
            progress_callback=on_progress,
            tracker=tracker,
        )

    await _run_single_output_job(job_id, work)


async def run_rotate_job(job_id: str, input_path: Path, op: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return rotate_service.rotate_video(
            input_path, out_dir, op, progress_callback=on_progress, tracker=tracker
        )

    await _run_single_output_job(job_id, work)


async def run_resize_job(
    job_id: str,
    input_path: Path,
    preset: str | None,
    width: int | None,
    height: int | None,
    fit: str,
) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return resize_service.resize_video(
            input_path,
            out_dir,
            preset=preset,
            width=width,
            height=height,
            fit=fit,
            progress_callback=on_progress,
            tracker=tracker,
        )

    await _run_single_output_job(job_id, work)


async def _run_file_job(
    job_id: str,
    work: Callable[[Callable[[float, str], None]], Path | list[Path]],
) -> None:
    """Shared orchestrator for image/PDF tools (single or multi output)."""
    db = SessionLocal()
    last_write = 0.0

    def on_progress(percent: float, stage: str) -> None:
        nonlocal last_write
        now = time.monotonic()
        if now - last_write < 0.5 and percent < 99:
            return
        last_write = now
        update_job_progress(
            db,
            job_id,
            progress=int(percent),
            stage=stage,
            status="processing",
        )

    try:
        update_job_progress(db, job_id, status="processing", stage="processing", progress=1)
        result = await asyncio.to_thread(work, on_progress)

        if runner.is_cancelled(job_id):
            update_job_progress(db, job_id, status="cancelled", stage="cancelled", progress=0)
            return

        paths = result if isinstance(result, list) else [result]
        for index, path in enumerate(paths, start=1):
            width = height = None
            if path.suffix.lower() in {
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".avif",
                ".gif",
                ".bmp",
                ".tif",
                ".tiff",
                ".ico",
            }:
                try:
                    from app.services.image.io import open_image

                    with open_image(path) as im:
                        width, height = im.width, im.height
                except Exception:  # noqa: BLE001
                    pass

            add_job_file(
                db,
                job_id=job_id,
                role="output",
                absolute_path=path,
                original_name=path.name,
                part_index=index,
                mime_type=_mime_for_path(path),
                width=width,
                height=height,
            )

        update_job_progress(db, job_id, status="completed", stage="packaging", progress=100)
        logger.info("file_job_completed", job_id=job_id, outputs=len(paths))
    except AppError as exc:
        update_job_progress(
            db,
            job_id,
            status="failed",
            stage="failed",
            error_code=exc.code,
            error_message=exc.message,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("file_job_failed", job_id=job_id)
        update_job_progress(
            db,
            job_id,
            status="failed",
            stage="failed",
            error_code="INTERNAL_ERROR",
            error_message=str(exc) or "Processing failed",
        )
    finally:
        db.close()


# Back-compat alias for image workers
_run_image_job = _run_file_job


async def run_img_compress_job(job_id: str, input_path: Path, preset: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return img_compress.compress_image(input_path, out_dir, preset, on_progress)

    await _run_image_job(job_id, work)


async def run_img_target_job(job_id: str, input_path: Path, kb: int) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return img_compress.compress_to_kb(input_path, out_dir, kb, on_progress)

    await _run_image_job(job_id, work)


async def run_img_convert_job(job_id: str, input_path: Path, fmt: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return img_convert.convert_image(input_path, out_dir, fmt, on_progress)

    await _run_image_job(job_id, work)


async def run_img_resize_job(
    job_id: str,
    input_path: Path,
    *,
    width: int | None,
    height: int | None,
    mode: str,
    crop_x: int | None,
    crop_y: int | None,
    crop_w: int | None,
    crop_h: int | None,
) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return img_resize.resize_image(
            input_path,
            out_dir,
            width=width,
            height=height,
            mode=mode,
            crop_x=crop_x,
            crop_y=crop_y,
            crop_w=crop_w,
            crop_h=crop_h,
            progress_callback=on_progress,
        )

    await _run_image_job(job_id, work)


async def run_img_pdf_job(job_id: str, input_path: Path, direction: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> list[Path]:
        return img_pdf.convert_pdf(
            input_path, out_dir, direction=direction, progress_callback=on_progress
        )

    await _run_image_job(job_id, work)


async def run_img_watermark_job(
    job_id: str,
    input_path: Path,
    *,
    text: str | None,
    mark_path: Path | None,
    position: str,
    opacity: float,
    scale: float,
) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return img_watermark.add_watermark(
            input_path,
            out_dir,
            text=text,
            mark_path=mark_path,
            position=position,
            opacity=opacity,
            scale=scale,
            progress_callback=on_progress,
        )

    await _run_image_job(job_id, work)


async def run_img_meme_job(
    job_id: str,
    input_path: Path,
    *,
    top: str,
    bottom: str,
    font_size: int | None,
) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return img_meme.make_meme(
            input_path,
            out_dir,
            top=top,
            bottom=bottom,
            font_size=font_size,
            progress_callback=on_progress,
        )

    await _run_image_job(job_id, work)


async def run_img_exif_job(job_id: str, input_path: Path, mode: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return img_exif.process_exif(input_path, out_dir, mode=mode, progress_callback=on_progress)

    await _run_image_job(job_id, work)


async def run_img_favicon_job(job_id: str, input_path: Path) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> list[Path]:
        return img_favicon.make_favicon(input_path, out_dir, progress_callback=on_progress)

    await _run_image_job(job_id, work)


# --- PDF / document jobs -------------------------------------------------


async def run_pdf_merge_job(job_id: str, paths: list[Path]) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_merge.merge_pdfs(paths, out_dir, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_pdf_split_job(
    job_id: str, input_path: Path, mode: str, ranges: str | None
) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> list[Path]:
        return pdf_split.split_pdf(
            input_path, out_dir, mode=mode, ranges=ranges, progress_callback=on_progress
        )

    await _run_file_job(job_id, work)


async def run_pdf_compress_job(job_id: str, input_path: Path, preset: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_compress.compress_pdf(input_path, out_dir, preset, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_pdf_to_word_job(job_id: str, input_path: Path) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_convert.pdf_to_word(input_path, out_dir, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_pdf_from_word_job(job_id: str, input_path: Path) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_convert.word_to_pdf(input_path, out_dir, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_pdf_to_excel_job(job_id: str, input_path: Path) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_convert.pdf_to_excel(input_path, out_dir, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_pdf_to_jpg_job(job_id: str, input_path: Path, dpi: int) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> list[Path]:
        return pdf_convert.pdf_to_jpg(input_path, out_dir, dpi=dpi, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_pdf_from_jpg_job(job_id: str, paths: list[Path]) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_convert.jpg_to_pdf(paths, out_dir, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_pdf_rotate_job(job_id: str, input_path: Path, angle: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_secure.rotate_pdf(input_path, out_dir, angle, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_pdf_unlock_job(job_id: str, input_path: Path, password: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_secure.unlock_pdf(input_path, out_dir, password, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_pdf_protect_job(
    job_id: str, input_path: Path, user_password: str, owner_password: str | None
) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_secure.protect_pdf(
            input_path,
            out_dir,
            user_password,
            owner_password,
            progress_callback=on_progress,
        )

    await _run_file_job(job_id, work)


async def run_pdf_ocr_job(job_id: str, input_path: Path, lang: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_ocr.ocr_pdf(input_path, out_dir, lang=lang, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_pdf_esign_job(
    job_id: str,
    input_path: Path,
    signature_path: Path,
    *,
    page: int,
    position: str,
    scale: float,
) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_annotate.esign_pdf(
            input_path,
            out_dir,
            signature_path,
            page=page,
            position=position,
            scale=scale,
            progress_callback=on_progress,
        )

    await _run_file_job(job_id, work)


async def run_pdf_watermark_job(
    job_id: str,
    input_path: Path,
    *,
    text: str,
    opacity: float,
    angle: int,
) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_annotate.watermark_pdf(
            input_path,
            out_dir,
            text=text,
            opacity=opacity,
            angle=angle,
            progress_callback=on_progress,
        )

    await _run_file_job(job_id, work)


async def run_pdf_pagenum_job(
    job_id: str,
    input_path: Path,
    *,
    position: str,
    start: int,
    format_str: str,
) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return pdf_annotate.add_page_numbers(
            input_path,
            out_dir,
            position=position,
            start=start,
            format_str=format_str,
            progress_callback=on_progress,
        )

    await _run_file_job(job_id, work)


# --- Audio jobs -----------------------------------------------------------


async def run_audio_convert_job(
    job_id: str, input_path: Path, fmt: str, bitrate: str
) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return aud_convert.convert_audio(
            input_path, out_dir, fmt, bitrate, progress_callback=on_progress, tracker=tracker
        )

    await _run_single_output_job(job_id, work)


async def run_audio_compress_job(job_id: str, input_path: Path, preset: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return aud_compress.compress_audio(
            input_path, out_dir, preset, progress_callback=on_progress, tracker=tracker
        )

    await _run_single_output_job(job_id, work)


async def run_audio_trim_job(
    job_id: str, input_path: Path, start: float, end: float, mode: str
) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return aud_trim.trim_audio(
            input_path,
            out_dir,
            start,
            end,
            mode,
            progress_callback=on_progress,
            tracker=tracker,
        )

    await _run_single_output_job(job_id, work)


async def run_audio_merge_job(job_id: str, paths: list[Path]) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return aud_merge.merge_audio(paths, out_dir, progress_callback=on_progress, tracker=tracker)

    await _run_single_output_job(job_id, work)


async def run_audio_denoise_job(job_id: str, input_path: Path, preset: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(tracker: FfmpegProcess, on_progress: Callable[[float, str], None]) -> Path:
        return aud_denoise.denoise_audio(
            input_path, out_dir, preset, progress_callback=on_progress, tracker=tracker
        )

    await _run_single_output_job(job_id, work)


async def run_audio_separate_job(job_id: str, input_path: Path) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> list[Path]:
        return aud_separate.separate_vocals(input_path, out_dir, progress_callback=on_progress)

    await _run_file_job(job_id, work)


async def run_md_convert_job(job_id: str, input_path: Path, target: str) -> None:
    out_dir = job_output_dir(job_id)

    def work(on_progress: Callable[[float, str], None]) -> Path:
        return md_convert.convert_markdown(
            input_path, out_dir, target, progress_callback=on_progress
        )

    await _run_file_job(job_id, work)
