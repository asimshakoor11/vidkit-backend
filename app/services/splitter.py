"""FFmpeg video splitting (fast copy and precise re-encode)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe

logger = get_logger(__name__)

# Backward-compatible alias used by workers
SplitProcess = FfmpegProcess


def build_fast_cmd(input_path: Path, output_pattern: Path, chunk_seconds: int) -> list[str]:
    """Build ffmpeg args for lossless stream-copy segmentation."""
    return [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0",
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-reset_timestamps",
        "1",
        "-avoid_negative_ts",
        "make_zero",
        *progress_flags(),
        str(output_pattern),
    ]


def build_precise_cmd(
    input_path: Path,
    output_pattern: Path,
    chunk_seconds: int,
    audio_copy: bool = True,
) -> list[str]:
    """Build ffmpeg args for precise re-encode segmentation."""
    audio_args = ["-c:a", "copy"] if audio_copy else ["-c:a", "aac", "-b:a", "192k"]
    return [
        ffmpeg_bin(),
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0",
        "-c:v",
        "libx264",
        "-crf",
        "17",
        "-preset",
        "medium",
        *audio_args,
        "-force_key_frames",
        f"expr:gte(t,n_forced*{chunk_seconds})",
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-reset_timestamps",
        "1",
        *progress_flags(),
        str(output_pattern),
    ]


def split_video(
    input_path: Path,
    output_dir: Path,
    chunk_seconds: int,
    mode: str,
    info: ProbeInfo | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> list[Path]:
    """
    Split a video into parts.

    Fast mode uses stream copy; precise mode re-encodes with libx264 CRF 17.
    Output files keep the same extension as the input.
    """
    if chunk_seconds < 1:
        raise AppError("INVALID_CHUNK_LENGTH", "Chunk length must be at least 1 second.")

    info = info or probe(input_path)
    if info.duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine video duration.")
    if chunk_seconds >= info.duration:
        raise AppError(
            "INVALID_CHUNK_LENGTH",
            "Chunk length must be shorter than the video duration.",
        )

    settings = get_settings()
    if info.duration > settings.max_video_duration_seconds:
        raise AppError(
            "DURATION_LIMIT",
            f"Video exceeds the {settings.max_video_duration_min} minute limit.",
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    ext = input_path.suffix.lower() or ".mp4"
    pattern = output_dir / f"part_%03d{ext}"

    if mode == "fast":
        cmd = build_fast_cmd(input_path, pattern, chunk_seconds)
        run_ffmpeg(cmd, info.duration, tracker, progress_callback, stage="splitting")
    elif mode == "precise":
        cmd = build_precise_cmd(input_path, pattern, chunk_seconds, audio_copy=True)
        try:
            run_ffmpeg(cmd, info.duration, tracker, progress_callback, stage="splitting")
        except AppError:
            logger.warning("precise_audio_copy_failed_retrying_aac")
            for leftover in output_dir.glob(f"part_*{ext}"):
                leftover.unlink(missing_ok=True)
            cmd = build_precise_cmd(input_path, pattern, chunk_seconds, audio_copy=False)
            run_ffmpeg(cmd, info.duration, tracker, progress_callback, stage="splitting")
    else:
        raise AppError("INVALID_CHUNK_LENGTH", "Mode must be 'fast' or 'precise'.")

    parts = sorted(output_dir.glob(f"part_*{ext}"))
    if not parts:
        raise AppError("INTERNAL_ERROR", "Split produced no output files.", status_code=500)

    verified: list[Path] = []
    for part in parts:
        part_info = probe(part)
        if part_info.duration <= 0:
            raise AppError("INTERNAL_ERROR", f"Invalid split part: {part.name}", status_code=500)
        verified.append(part)

    if progress_callback:
        progress_callback(100.0, "packaging")
    return verified
