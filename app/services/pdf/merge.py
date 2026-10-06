"""Merge multiple PDFs into one."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter

from app.core.errors import AppError
from app.services.pdf.io import ProgressCb, open_reader, out_name, write_writer


def merge_pdfs(
    paths: list[Path],
    output_dir: Path,
    progress_callback: ProgressCb = None,
) -> Path:
    """Merge PDFs in order into a single file."""
    if len(paths) < 2:
        raise AppError("UNSUPPORTED_FORMAT", "Upload at least two PDF files to merge.")

    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(5, "merging")
    writer = PdfWriter()
    for index, path in enumerate(paths):
        reader = open_reader(path)
        for page in reader.pages:
            writer.add_page(page)
        report(5 + (index + 1) / len(paths) * 85, "merging")

    stem = paths[0].stem
    out = output_dir / out_name(stem, "merged")
    write_writer(writer, out)
    report(100, "done")
    return out
