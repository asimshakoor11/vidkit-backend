"""Merge multiple audio files into one MP3."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.audio.io import out_path
from app.services.ffmpeg import FfmpegProcess, ProgressCb, ffmpeg_bin, progress_flags, run_ffmpeg
from app.services.ffprobe import ProbeInfo, probe


def merge_audio(
    input_paths: list[Path],
    output_dir: Path,
    infos: list[ProbeInfo] | None = None,
    progress_callback: ProgressCb | None = None,
    tracker: FfmpegProcess | None = None,
) -> Path:
    """Concatenate audio clips; re-encode to MP3 for compatibility."""
    if len(input_paths) < 2:
        raise AppError("UNSUPPORTED_FORMAT", "Upload at least two audio files to merge.")

    infos = infos or [probe(p) for p in input_paths]
    total_duration = sum(max(i.duration, 0.0) for i in infos)
    if total_duration <= 0:
        raise AppError("UNSUPPORTED_FORMAT", "Could not determine audio duration.")

    out = out_path(output_dir, input_paths[0].stem, "merged", ".mp3")
    list_file = output_dir / "concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in input_paths),
        encoding="utf-8",
    )

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-vn",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        *progress_flags(),
        str(out),
    ]
    try:
        run_ffmpeg(cmd, total_duration, tracker, progress_callback, fail_message="Audio merge failed.")
    finally:
        list_file.unlink(missing_ok=True)

    if not out.exists():
        raise AppError("INTERNAL_ERROR", "Merge produced no output.", status_code=500)
    if progress_callback:
        progress_callback(100.0, "packaging")
    return out
