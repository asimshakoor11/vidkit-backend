"""Shared pypdf open/write helpers for PDF tools."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.core.errors import AppError

ProgressCb = Callable[[float, str], None] | None


def open_reader(path: Path, password: str | None = None) -> PdfReader:
    """Open a PDF; decrypt with password when needed."""
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001
        raise AppError("UNSUPPORTED_FORMAT", "Could not read this PDF file.") from exc

    if reader.is_encrypted:
        if not password:
            raise AppError(
                "BAD_PASSWORD",
                "This PDF is password-protected. Provide the password to unlock it.",
            )
        try:
            result = reader.decrypt(password)
        except Exception as exc:  # noqa: BLE001
            raise AppError("BAD_PASSWORD", "Incorrect PDF password.") from exc
        if result == 0:
            raise AppError("BAD_PASSWORD", "Incorrect PDF password.")
    return reader


def page_count(path: Path, password: str | None = None) -> int:
    """Return page count for a PDF."""
    return len(open_reader(path, password).pages)


def write_writer(writer: PdfWriter, out_path: Path) -> Path:
    """Write a PdfWriter to disk."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out_path.open("wb") as fh:
            writer.write(fh)
    except Exception as exc:  # noqa: BLE001
        raise AppError("CONVERSION_FAILED", "Failed to write PDF output.") from exc
    return out_path


def copy_pages(reader: PdfReader, writer: PdfWriter, indices: list[int] | None = None) -> None:
    """Append pages from reader into writer. indices are 0-based."""
    pages = reader.pages if indices is None else [reader.pages[i] for i in indices]
    for page in pages:
        writer.add_page(page)


def out_name(stem: str, suffix: str, ext: str = ".pdf") -> str:
    """Build a safe output filename."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in stem)[:80] or "document"
    return f"{safe}_{suffix}{ext}"
