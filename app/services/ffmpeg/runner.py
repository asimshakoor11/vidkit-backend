"""Cancelable FFmpeg subprocess runner with progress parsing."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable

from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

ProgressCb = Callable[[float, str], None]


class FfmpegProcess:
    """Tracks a running ffmpeg process so it can be cancelled."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


def _parse_progress(line: str, duration_us: float) -> float | None:
    match = re.match(r"out_time_ms=(\d+)", line.strip())
    if not match or duration_us <= 0:
        if line.strip() == "progress=end":
            return 100.0
        return None
    out_us = float(match.group(1))
    return min(99.0, (out_us / duration_us) * 100.0)


def run_ffmpeg(
    cmd: list[str],
    duration: float,
    tracker: FfmpegProcess | None = None,
    progress_callback: ProgressCb | None = None,
    stage: str = "processing",
    fail_message: str = "Video processing failed.",
) -> None:
    """Run an ffmpeg argv list; parse -progress pipe:1 into 0–100 callbacks."""
    logger.info("ffmpeg_start", cmd=cmd)
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise AppError(
            "INTERNAL_ERROR",
            "ffmpeg is not installed or not on PATH.",
            status_code=500,
        ) from exc

    if tracker is not None:
        tracker.process = process

    duration_us = max(duration, 0.001) * 1_000_000
    assert process.stdout is not None
    for line in process.stdout:
        if tracker and tracker.cancelled:
            process.terminate()
            raise AppError("JOB_NOT_FOUND", "Job was cancelled.", status_code=499)
        if progress_callback:
            pct = _parse_progress(line, duration_us)
            if pct is not None:
                progress_callback(pct, stage)

    code = process.wait()
    if tracker and tracker.cancelled:
        raise AppError("JOB_NOT_FOUND", "Job was cancelled.", status_code=499)
    if code != 0:
        logger.error("ffmpeg_failed", code=code)
        raise AppError("INTERNAL_ERROR", fail_message, status_code=500)
