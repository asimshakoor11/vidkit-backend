"""Watermark, page numbers, and visual eSign overlays for PDFs."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

from app.core.errors import AppError
from app.services.pdf.io import ProgressCb, open_reader, out_name, write_writer

_POS_MAP = {
    "tl": (0.12, 0.88),
    "tc": (0.5, 0.88),
    "tr": (0.88, 0.88),
    "bl": (0.12, 0.08),
    "bc": (0.5, 0.08),
    "br": (0.88, 0.08),
    "center": (0.5, 0.5),
}


def _overlay_page(
    width: float,
    height: float,
    draw_fn,
) -> PdfReader:
    """Build a single-page overlay PDF in memory and return a reader."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    draw_fn(c, width, height)
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def watermark_pdf(
    input_path: Path,
    output_dir: Path,
    *,
    text: str = "",
    opacity: float = 0.3,
    angle: int = 45,
    progress_callback: ProgressCb = None,
) -> Path:
    """Stamp diagonal text watermark on every page."""
    text = (text or "").strip()
    if not text:
        raise AppError("UNSUPPORTED_FORMAT", "Watermark text is required.")
    opacity = max(0.05, min(opacity, 1.0))

    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(10, "watermarking")
    reader = open_reader(input_path)
    writer = PdfWriter(clone_from=reader)

    for i, page in enumerate(writer.pages, start=1):
        box = page.mediabox
        w, h = float(box.width), float(box.height)

        def draw(c: canvas.Canvas, width: float, height: float, _text=text) -> None:
            c.saveState()
            c.setFillColor(Color(0.4, 0.4, 0.4, alpha=opacity))
            c.translate(width / 2, height / 2)
            c.rotate(angle)
            font_size = max(24, min(width, height) * 0.08)
            c.setFont("Helvetica-Bold", font_size)
            c.drawCentredString(0, 0, _text)
            c.restoreState()

        overlay = _overlay_page(w, h, draw)
        page.merge_page(overlay.pages[0])
        report(10 + i / len(writer.pages) * 85, "watermarking")

    out = output_dir / out_name(input_path.stem, "watermarked")
    write_writer(writer, out)
    report(100, "done")
    return out


def add_page_numbers(
    input_path: Path,
    output_dir: Path,
    *,
    position: str = "bc",
    start: int = 1,
    format_str: str = "{n}",
    progress_callback: ProgressCb = None,
) -> Path:
    """Add page numbers to every page."""
    if position not in _POS_MAP:
        raise AppError("UNSUPPORTED_FORMAT", "Invalid page number position.")
    start = max(1, start)
    fmt = format_str or "{n}"

    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(10, "numbering")
    reader = open_reader(input_path)
    writer = PdfWriter(clone_from=reader)
    fx, fy = _POS_MAP[position]
    total = len(writer.pages)

    for i, page in enumerate(writer.pages):
        box = page.mediabox
        w, h = float(box.width), float(box.height)
        number = start + i
        label = (
            fmt.replace("{n}", str(number))
            .replace("{total}", str(total))
            .replace("{N}", str(number))
        )

        def draw(c: canvas.Canvas, width: float, height: float, _label=label) -> None:
            c.setFont("Helvetica", 10)
            c.setFillColor(Color(0.2, 0.2, 0.2, alpha=1))
            c.drawCentredString(width * fx, height * fy, _label)

        overlay = _overlay_page(w, h, draw)
        page.merge_page(overlay.pages[0])
        report(10 + (i + 1) / total * 85, "numbering")

    out = output_dir / out_name(input_path.stem, "numbered")
    write_writer(writer, out)
    report(100, "done")
    return out


def esign_pdf(
    input_path: Path,
    output_dir: Path,
    signature_path: Path,
    *,
    page: int = 1,
    position: str = "br",
    scale: float = 0.2,
    progress_callback: ProgressCb = None,
) -> Path:
    """Overlay a signature image on one page (visual stamp only)."""
    if position not in _POS_MAP:
        raise AppError("UNSUPPORTED_FORMAT", "Invalid signature position.")
    scale = max(0.05, min(scale, 0.8))
    page = max(1, page)

    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(10, "signing")
    if not signature_path.exists():
        raise AppError("UNSUPPORTED_FORMAT", "Signature image is required.")

    reader = open_reader(input_path)
    if page > len(reader.pages):
        raise AppError(
            "UNSUPPORTED_FORMAT",
            f"Page {page} does not exist (PDF has {len(reader.pages)} pages).",
        )

    writer = PdfWriter(clone_from=reader)
    fx, fy = _POS_MAP[position]
    target_idx = page - 1
    pdf_page = writer.pages[target_idx]
    box = pdf_page.mediabox
    w, h = float(box.width), float(box.height)
    sig_w = w * scale
    sig_h = sig_w * 0.4

    def draw(
        c: canvas.Canvas,
        width: float,
        height: float,
        _sig=str(signature_path),
        _sw=sig_w,
        _sh=sig_h,
    ) -> None:
        x = width * fx - _sw / 2
        y = height * fy - _sh / 2
        c.drawImage(
            _sig,
            x,
            y,
            width=_sw,
            height=_sh,
            mask="auto",
            preserveAspectRatio=True,
            anchor="c",
        )

    try:
        overlay = _overlay_page(w, h, draw)
        pdf_page.merge_page(overlay.pages[0])
    except Exception as exc:  # noqa: BLE001
        raise AppError("CONVERSION_FAILED", "Could not place signature image.") from exc

    report(90, "signing")
    out = output_dir / out_name(input_path.stem, "signed")
    write_writer(writer, out)
    report(100, "done")
    return out
