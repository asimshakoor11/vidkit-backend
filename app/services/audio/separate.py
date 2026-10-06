"""Separate vocals and instrumental stems with Demucs."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.services.audio.io import out_path
from app.services.ffmpeg import ProgressCb

logger = get_logger(__name__)


def separate_vocals(
    input_path: Path,
    output_dir: Path,
    progress_callback: ProgressCb | None = None,
) -> list[Path]:
    """
    Run Demucs two-stem separation (vocals + no_vocals).

    Returns [vocals_path, instrumental_path].
    """
    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(5, "separating")
    settings = get_settings()
    work_dir = output_dir / "_demucs"
    work_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems=vocals",
        "-o",
        str(work_dir),
        str(input_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.audio_separate_timeout_sec,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AppError(
            "DEPENDENCY_MISSING",
            "Demucs is not installed. Run: pip install demucs",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AppError("CONVERSION_FAILED", "Vocal separation timed out.") from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-800:]
        logger.warning("demucs_failed", stderr=err)
        if "No module named demucs" in err or "No module named 'demucs'" in err:
            raise AppError(
                "DEPENDENCY_MISSING",
                "Demucs is not installed. Run: pip install demucs",
            )
        raise AppError("CONVERSION_FAILED", "Vocal separation failed.")

    report(80, "packaging")
    # Demucs writes: work_dir/<model>/<stem>/vocals.wav and no_vocals.wav
    vocals_src = next(work_dir.rglob("vocals.wav"), None)
    instr_src = next(work_dir.rglob("no_vocals.wav"), None)
    if vocals_src is None or instr_src is None:
        raise AppError("CONVERSION_FAILED", "Demucs produced incomplete stems.")

    vocals_out = out_path(output_dir, input_path.stem, "vocals", ".wav")
    instr_out = out_path(output_dir, input_path.stem, "instrumental", ".wav")
    shutil.copy2(vocals_src, vocals_out)
    shutil.copy2(instr_src, instr_out)

    # Cleanup work tree
    shutil.rmtree(work_dir, ignore_errors=True)

    report(100, "done")
    return [vocals_out, instr_out]
