"""Image ↔ PDF conversion via Pillow and PyMuPDF."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.core.errors import AppError
from app.services.image.io import flatten_rgb, open_image

DIRECTIONS = {"to_pdf", "from_pdf"}


def convert_pdf(
    input_path: Path,
    output_dir: Path,
    *,
    direction: str,
    progress_callback=None,
) -> list[Path]:
    if direction not in DIRECTIONS:
        raise AppError("UNSUPPORTED_FORMAT", "Direction must be to_pdf or from_pdf.")

    output_dir.mkdir(parents=True, exist_ok=True)

    if direction == "to_pdf":
        return [_to_pdf(input_path, output_dir, progress_callback)]
    return _from_pdf(input_path, output_dir, progress_callback)


def _to_pdf(input_path: Path, output_dir: Path, progress_callback) -> Path:
    if progress_callback:
        progress_callback(20, "opening")
    if input_path.suffix.lower() == ".pdf":
        raise AppError("UNSUPPORTED_FORMAT", "Upload an image to convert to PDF.")
    img = flatten_rgb(open_image(input_path))
    out = output_dir / f"{input_path.stem}.pdf"
    if progress_callback:
        progress_callback(70, "writing")
    img.save(out, format="PDF", resolution=100.0)
    if progress_callback:
        progress_callback(100, "done")
    return out


def _from_pdf(input_path: Path, output_dir: Path, progress_callback) -> list[Path]:
    if input_path.suffix.lower() != ".pdf":
        raise AppError("UNSUPPORTED_FORMAT", "Upload a PDF to convert to images.")
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise AppError("INTERNAL_ERROR", "PDF support is not installed.") from exc

    if progress_callback:
        progress_callback(10, "opening")

    doc = fitz.open(input_path)
    try:
        if doc.page_count < 1:
            raise AppError("UNSUPPORTED_FORMAT", "This PDF has no pages.")
        paths: list[Path] = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            out = output_dir / f"{input_path.stem}_p{i + 1:02d}.png"
            pix.save(out.as_posix())
            # Ensure valid PNG via Pillow
            with Image.open(out) as im:
                im.load()
            paths.append(out)
            if progress_callback:
                progress_callback(10 + int(85 * (i + 1) / doc.page_count), "rendering")
        if progress_callback:
            progress_callback(100, "done")
        return paths
    finally:
        doc.close()
