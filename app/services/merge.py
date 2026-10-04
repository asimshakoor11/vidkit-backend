"""Merge multiple video clips into one file."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe


def _codecs_match(infos: list[ProbeInfo]) -> bool:
    if not infos:
        return False
    first = infos[0]
    return all(
        i.codec_video == first.codec_video
        and i.codec_audio == first.codec_audio
        and i.width == first.width
        and i.height == first.height
        for i in infos
    )


def merge_videos(
    input_paths: list[Path],
    output_dir: Path,
    infos: list[ProbeInfo] | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Concatenate clips. Stream-copy when compatible; else re-encode to mp4."""
    if len(input_paths) < 2:
        raise AppError("UNSUPPORTED_FORMAT", "Upload at least two videos to merge.")

    infos = infos or [probe(p) for p in input_paths]
    total_duration = sum(max(i.duration, 0.0) for i in infos)
    if total_duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine video duration.")

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "merged.mp4"
    list_file = output_dir / "concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in input_paths),
        encoding="utf-8",
    )

    if _codecs_match(infos):
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            *progress_flags(),
            str(out),
        ]
        try:
            run_ffmpeg(cmd, total_duration, tracker, progress_callback, fail_message="Merge failed.")
        except AppError:
            out.unlink(missing_ok=True)
            cmd = _reencode_cmd(list_file, out)
            run_ffmpeg(cmd, total_duration, tracker, progress_callback, fail_message="Merge failed.")
    else:
        cmd = _reencode_cmd(list_file, out)
        run_ffmpeg(cmd, total_duration, tracker, progress_callback, fail_message="Merge failed.")

    list_file.unlink(missing_ok=True)
    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Merge produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out


def _reencode_cmd(list_file: Path, out: Path) -> list[str]:
    return [
        ffmpeg_bin(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-preset",
        "medium",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        *progress_flags(),
        str(out),
    ]
