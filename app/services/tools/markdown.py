"""Markdown conversion via Pandoc."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

ProgressCb = Callable[[float, str], None] | None

TARGETS = frozenset({"html", "pdf"})


def pandoc_bin() -> str:
    settings = get_settings()
    configured = settings.pandoc_path
    path = Path(configured)
    if path.is_file():
        return str(path)
    found = shutil.which(configured) or shutil.which("pandoc")
    if found:
        return found
    raise AppError(
        "DEPENDENCY_MISSING",
        "Pandoc is not installed. Install it and set PANDOC_PATH in .env.",
    )


def convert_markdown(
    input_path: Path,
    output_dir: Path,
    target: str,
    progress_callback: ProgressCb = None,
) -> Path:
    """Convert a Markdown file to HTML or PDF with Pandoc."""
    if target not in TARGETS:
        raise AppError("UNSUPPORTED_FORMAT", "Target must be html or pdf.")

    output_dir.mkdir(parents=True, exist_ok=True)
    ext = ".html" if target == "html" else ".pdf"
    dest = output_dir / f"{input_path.stem}{ext}"
    pandoc = pandoc_bin()
    settings = get_settings()

    if progress_callback:
        progress_callback(10, "converting")

    cmd = [
        pandoc,
        "-f",
        "markdown",
        "-t",
        target,
        "-o",
        str(dest),
        str(input_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.markdown_timeout_sec,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError("CONVERSION_FAILED", "Markdown conversion timed out.") from exc
    except FileNotFoundError as exc:
        raise AppError("DEPENDENCY_MISSING", "Pandoc is not installed.") from exc

    if proc.returncode != 0 or not dest.exists():
        logger.warning("pandoc_failed", stderr=(proc.stderr or "")[-500:])
        hint = " Conversion failed."
        if target == "pdf":
            hint = " PDF conversion failed. Ensure Pandoc has a PDF engine (e.g. pdflatex)."
        raise AppError("CONVERSION_FAILED", hint.strip())

    if progress_callback:
        progress_callback(100, "done")
    return dest
