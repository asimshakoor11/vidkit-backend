"""Compress PDF via Ghostscript."""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.services.pdf.bins import gs_bin
from app.services.pdf.io import ProgressCb, out_name

logger = get_logger(__name__)

_SETTINGS_MAP = {
    "screen": "/screen",
    "ebook": "/ebook",
    "printer": "/printer",
}


def compress_pdf(
    input_path: Path,
    output_dir: Path,
    preset: str = "ebook",
    progress_callback: ProgressCb = None,
) -> Path:
    """Compress a PDF with Ghostscript PDFSETTINGS."""
    if preset not in _SETTINGS_MAP:
        raise AppError("UNSUPPORTED_FORMAT", "Preset must be screen, ebook, or printer.")

    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(10, "compressing")
    gs = gs_bin()
    out = output_dir / out_name(input_path.stem, "compressed")
    settings = get_settings()
    cmd = [
        gs,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={_SETTINGS_MAP[preset]}",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={out}",
        str(input_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.pdf_convert_timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError("CONVERSION_FAILED", "PDF compression timed out.") from exc
    except FileNotFoundError as exc:
        raise AppError("DEPENDENCY_MISSING", "Ghostscript is not installed.") from exc

    if proc.returncode != 0 or not out.exists() or out.stat().st_size < 5:
        logger.warning("gs_compress_failed", stderr=proc.stderr[-500:] if proc.stderr else "")
        raise AppError("CONVERSION_FAILED", "PDF compression failed.")

    report(100, "done")
    return out
