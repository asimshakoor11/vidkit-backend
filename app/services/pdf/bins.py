"""Resolve external binaries used by PDF tools."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError


def _resolve(configured: str, *fallbacks: str) -> str:
    candidates = [configured, *fallbacks]
    for name in candidates:
        if not name:
            continue
        path = Path(name)
        if path.is_file():
            return str(path)
        found = shutil.which(name)
        if found:
            return found
    raise AppError(
        "DEPENDENCY_MISSING",
        f"Required tool not found ({configured}). Install it and set the path in .env.",
    )


def gs_bin() -> str:
    """Ghostscript executable (gs on Unix, gswin64c on Windows)."""
    settings = get_settings()
    return _resolve(settings.gs_path, "gs", "gswin64c", "gswin32c")


def soffice_bin() -> str:
    """LibreOffice headless converter."""
    settings = get_settings()
    return _resolve(
        settings.libreoffice_path,
        "soffice",
        "libreoffice",
    )


def tesseract_bin() -> str:
    """Tesseract OCR binary."""
    settings = get_settings()
    return _resolve(settings.tesseract_path, "tesseract")


def poppler_path() -> str | None:
    """Optional Poppler bin directory for pdf2image."""
    settings = get_settings()
    raw = (settings.poppler_path or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_dir():
        return str(path)
    raise AppError(
        "DEPENDENCY_MISSING",
        "POPPLER_PATH must point to a directory containing pdftoppm.",
    )
