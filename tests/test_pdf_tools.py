"""Unit tests for PDF document tools (pypdf / reportlab; skip binary tools)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.core.errors import AppError
from app.services.pdf import annotate as annotate_svc
from app.services.pdf import convert as convert_svc
from app.services.pdf import merge as merge_svc
from app.services.pdf import secure as secure_svc
from app.services.pdf import split as split_svc
from app.services.pdf.bins import gs_bin


def _make_pdf(path: Path, pages: int = 2, text: str = "VidKit") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=(400, 300))
    for i in range(pages):
        c.drawString(40, 150, f"{text} page {i + 1}")
        c.showPage()
    c.save()
    return path


def test_merge_and_split(tmp_path: Path) -> None:
    a = _make_pdf(tmp_path / "a.pdf", pages=2)
    b = _make_pdf(tmp_path / "b.pdf", pages=1, text="Second")
    merged = merge_svc.merge_pdfs([a, b], tmp_path / "out")
    assert merged.exists()
    assert len(PdfReader(str(merged)).pages) == 3

    parts = split_svc.split_pdf(merged, tmp_path / "parts", mode="each")
    assert len(parts) == 3

    ranged = split_svc.split_pdf(merged, tmp_path / "ranges", mode="ranges", ranges="1-2,3")
    assert len(ranged) == 2
    assert len(PdfReader(str(ranged[0])).pages) == 2


def test_rotate_protect_unlock(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path / "src.pdf", pages=1)
    rotated = secure_svc.rotate_pdf(src, tmp_path / "rot", "90")
    assert rotated.exists()

    protected = secure_svc.protect_pdf(src, tmp_path / "prot", "secret123")
    assert protected.exists()
    reader = PdfReader(str(protected))
    assert reader.is_encrypted

    unlocked = secure_svc.unlock_pdf(protected, tmp_path / "un", "secret123")
    assert unlocked.exists()
    assert not PdfReader(str(unlocked)).is_encrypted

    with pytest.raises(AppError) as exc:
        secure_svc.unlock_pdf(protected, tmp_path / "bad", "wrong")
    assert exc.value.code == "BAD_PASSWORD"


def test_watermark_and_page_numbers(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path / "src.pdf", pages=3)
    wm = annotate_svc.watermark_pdf(src, tmp_path / "wm", text="DRAFT", opacity=0.25)
    assert wm.exists()
    assert len(PdfReader(str(wm)).pages) == 3

    numbered = annotate_svc.add_page_numbers(
        src, tmp_path / "num", position="bc", start=1, format_str="{n}/{total}"
    )
    assert numbered.exists()


def test_esign_overlay(tmp_path: Path) -> None:
    from PIL import Image

    src = _make_pdf(tmp_path / "src.pdf", pages=2)
    sig = tmp_path / "sig.png"
    Image.new("RGBA", (200, 80), (20, 80, 200, 200)).save(sig, format="PNG")
    out = annotate_svc.esign_pdf(src, tmp_path / "signed", sig, page=2, position="br", scale=0.25)
    assert out.exists()
    assert len(PdfReader(str(out)).pages) == 2


def test_jpg_to_pdf_and_excel(tmp_path: Path) -> None:
    from PIL import Image

    imgs = []
    for i in range(2):
        p = tmp_path / f"img{i}.jpg"
        Image.new("RGB", (80, 60), (i * 40, 100, 150)).save(p, format="JPEG")
        imgs.append(p)
    pdf = convert_svc.jpg_to_pdf(imgs, tmp_path / "from_jpg")
    assert pdf.exists()
    assert len(PdfReader(str(pdf)).pages) == 2

    xlsx = convert_svc.pdf_to_excel(_make_pdf(tmp_path / "table.pdf", pages=1), tmp_path / "xlsx")
    assert xlsx.exists()
    assert xlsx.suffix == ".xlsx"


def test_compress_skipped_without_gs(tmp_path: Path) -> None:
    try:
        gs_bin()
    except AppError:
        pytest.skip("Ghostscript not installed")
    src = _make_pdf(tmp_path / "src.pdf", pages=1)
    from app.services.pdf import compress as compress_svc

    out = compress_svc.compress_pdf(src, tmp_path / "c", "ebook")
    assert out.exists()


def test_merge_requires_two_files(tmp_path: Path) -> None:
    a = _make_pdf(tmp_path / "a.pdf")
    with pytest.raises(AppError):
        merge_svc.merge_pdfs([a], tmp_path / "out")
