"""Unit and API tests for image tools."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from app.services.image import compress as compress_svc
from app.services.image import convert as convert_svc
from app.services.image import exif as exif_svc
from app.services.image import favicon as favicon_svc
from app.services.image import meme as meme_svc
from app.services.image import resize as resize_svc
from app.services.image import watermark as watermark_svc
from app.services.image.pdf import convert_pdf


def _png(tmp_path: Path, name: str = "sample.png", size=(120, 80), color=(30, 140, 220)) -> Path:
    path = tmp_path / name
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def test_compress_and_target_kb(tmp_path: Path) -> None:
    src = _png(tmp_path, size=(400, 300))
    out = compress_svc.compress_image(src, tmp_path / "out", "small")
    assert out.exists()
    assert out.stat().st_size > 0

    big = tmp_path / "big.jpg"
    Image.new("RGB", (800, 600), (200, 100, 50)).save(big, format="JPEG", quality=95)
    targeted = compress_svc.compress_to_kb(big, tmp_path / "out2", 40)
    assert targeted.exists()
    assert targeted.stat().st_size <= 40 * 1024


def test_convert_alpha_to_jpg(tmp_path: Path) -> None:
    src = tmp_path / "alpha.png"
    Image.new("RGBA", (64, 64), (255, 0, 0, 128)).save(src, format="PNG")
    out = convert_svc.convert_image(src, tmp_path / "c", "jpg")
    assert out.suffix == ".jpg"
    with Image.open(out) as im:
        assert im.mode == "RGB"


def test_resize_crop_and_fit(tmp_path: Path) -> None:
    src = _png(tmp_path, size=(200, 100))
    out = resize_svc.resize_image(
        src,
        tmp_path / "r",
        width=50,
        height=50,
        mode="fill",
        crop_x=10,
        crop_y=10,
        crop_w=100,
        crop_h=80,
    )
    with Image.open(out) as im:
        assert im.size == (50, 50)


def test_exif_strip_and_view(tmp_path: Path) -> None:
    src = tmp_path / "photo.jpg"
    img = Image.new("RGB", (80, 60), (10, 20, 30))
    exif = img.getexif()
    exif[271] = "VidKitCam"
    img.save(src, format="JPEG", exif=exif)

    viewed = exif_svc.process_exif(src, tmp_path / "v", mode="view")
    data = json.loads(viewed.read_text(encoding="utf-8"))
    assert data["width"] == 80

    cleaned = exif_svc.process_exif(src, tmp_path / "s", mode="strip")
    assert cleaned.exists()


def test_image_to_pdf_and_back(tmp_path: Path) -> None:
    src = _png(tmp_path)
    pdfs = convert_pdf(src, tmp_path / "pdf", direction="to_pdf")
    assert len(pdfs) == 1
    assert pdfs[0].suffix == ".pdf"

    pages = convert_pdf(pdfs[0], tmp_path / "pages", direction="from_pdf")
    assert len(pages) >= 1
    assert pages[0].suffix == ".png"


def test_watermark_and_meme(tmp_path: Path) -> None:
    src = _png(tmp_path, size=(320, 240))
    wm = watermark_svc.add_watermark(src, tmp_path / "wm", text="TEST", position="br")
    assert wm.exists()
    meme = meme_svc.make_meme(src, tmp_path / "meme", top="TOP", bottom="BOTTOM")
    assert meme.exists()


def test_favicon_pack(tmp_path: Path) -> None:
    src = _png(tmp_path, size=(256, 256))
    files = favicon_svc.make_favicon(src, tmp_path / "fav")
    names = {p.name for p in files}
    assert any(n.endswith(".zip") for n in names)
    assert "favicon.ico" in names


def test_api_image_compress_accepts(client, tmp_path: Path) -> None:
    src = _png(tmp_path)
    with src.open("rb") as fh:
        res = client.post(
            "/api/image/compress",
            files={"file": ("sample.png", fh, "image/png")},
            data={"preset": "balanced"},
        )
    assert res.status_code == 202, res.text
    assert res.json()["job_id"]


def test_api_image_convert_accepts(client, tmp_path: Path) -> None:
    src = _png(tmp_path)
    with src.open("rb") as fh:
        res = client.post(
            "/api/image/convert",
            files={"file": ("sample.png", fh, "image/png")},
            data={"fmt": "webp"},
        )
    assert res.status_code == 202, res.text
    assert res.json()["job_id"]


def test_api_rejects_video_on_image_endpoint(client, tmp_path: Path) -> None:
    fake = tmp_path / "clip.mp4"
    fake.write_bytes(b"not-a-real-video")
    with fake.open("rb") as fh:
        res = client.post(
            "/api/image/compress",
            files={"file": ("clip.mp4", fh, "video/mp4")},
            data={"preset": "balanced"},
        )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "UNSUPPORTED_FORMAT"
