"""OCR scanned PDFs into searchable PDFs via Tesseract."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.core.logging import get_logger
from app.services.pdf.bins import poppler_path, tesseract_bin
from app.services.pdf.io import ProgressCb, out_name

logger = get_logger(__name__)


def ocr_pdf(
    input_path: Path,
    output_dir: Path,
    lang: str = "eng",
    progress_callback: ProgressCb = None,
) -> Path:
    """
    Render pages → OCR with Tesseract → searchable PDF.

    Uses pdf2image + pytesseract PDF renderer.
    """
    import pytesseract
    from pdf2image import convert_from_path
    from pypdf import PdfReader, PdfWriter

    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(5, "preparing")
    tesseract = tesseract_bin()
    pytesseract.pytesseract.tesseract_cmd = tesseract

    kwargs: dict = {"dpi": 200}
    poppler = poppler_path()
    if poppler:
        kwargs["poppler_path"] = poppler

    try:
        images = convert_from_path(str(input_path), **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ocr_render_failed", error=str(exc))
        raise AppError(
            "CONVERSION_FAILED",
            "OCR failed to render PDF. Ensure Poppler is installed.",
        ) from exc

    if not images:
        raise AppError("UNSUPPORTED_FORMAT", "This PDF has no pages.")

    writer = PdfWriter()
    tmp_dir = output_dir / "_ocr_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        for i, img in enumerate(images, start=1):
            report(5 + i / len(images) * 85, "ocr")
            page_pdf = tmp_dir / f"page_{i:04d}.pdf"
            try:
                pdf_bytes = pytesseract.image_to_pdf_or_hocr(img, lang=lang, extension="pdf")
            except pytesseract.TesseractError as exc:
                raise AppError(
                    "CONVERSION_FAILED",
                    f"OCR failed. Is language '{lang}' installed for Tesseract?",
                ) from exc
            page_pdf.write_bytes(pdf_bytes)
            reader = PdfReader(str(page_pdf))
            for page in reader.pages:
                writer.add_page(page)

        out = output_dir / out_name(input_path.stem, "ocr")
        with out.open("wb") as fh:
            writer.write(fh)
    finally:
        for f in tmp_dir.glob("*"):
            f.unlink(missing_ok=True)
        tmp_dir.rmdir()

    report(100, "done")
    return out
