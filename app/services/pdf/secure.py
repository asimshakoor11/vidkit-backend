"""Rotate, unlock, and password-protect PDFs."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter
from pypdf.constants import UserAccessPermissions

from app.core.errors import AppError
from app.services.pdf.io import ProgressCb, open_reader, out_name, write_writer


def rotate_pdf(
    input_path: Path,
    output_dir: Path,
    angle: str,
    progress_callback: ProgressCb = None,
) -> Path:
    """Rotate every page by 90, 180, or 270 degrees clockwise."""
    if angle not in {"90", "180", "270"}:
        raise AppError("UNSUPPORTED_FORMAT", "Angle must be 90, 180, or 270.")
    degrees = int(angle)

    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(10, "rotating")
    reader = open_reader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(degrees)
        writer.add_page(page)
    out = output_dir / out_name(input_path.stem, f"rot{angle}")
    write_writer(writer, out)
    report(100, "done")
    return out


def unlock_pdf(
    input_path: Path,
    output_dir: Path,
    password: str,
    progress_callback: ProgressCb = None,
) -> Path:
    """Remove password protection from a PDF."""
    if not password:
        raise AppError("BAD_PASSWORD", "Password is required to unlock this PDF.")

    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(10, "unlocking")
    reader = open_reader(input_path, password=password)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    out = output_dir / out_name(input_path.stem, "unlocked")
    write_writer(writer, out)
    report(100, "done")
    return out


def protect_pdf(
    input_path: Path,
    output_dir: Path,
    user_password: str,
    owner_password: str | None = None,
    progress_callback: ProgressCb = None,
) -> Path:
    """Encrypt a PDF with a user (open) password."""
    if not user_password or len(user_password) < 4:
        raise AppError("UNSUPPORTED_FORMAT", "Password must be at least 4 characters.")

    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(10, "protecting")
    reader = open_reader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    owner = owner_password or user_password
    writer.encrypt(
        user_password=user_password,
        owner_password=owner,
        permissions_flag=UserAccessPermissions.PRINT
        | UserAccessPermissions.EXTRACT
        | UserAccessPermissions.MODIFY,
        algorithm="AES-256",
    )
    out = output_dir / out_name(input_path.stem, "protected")
    write_writer(writer, out)
    report(100, "done")
    return out
