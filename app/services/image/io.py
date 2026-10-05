"""Shared Pillow open/save helpers for image tools."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from app.core.errors import AppError

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

FMT_EXT = {
    "jpg": ".jpg",
    "jpeg": ".jpg",
    "png": ".png",
    "webp": ".webp",
    "avif": ".avif",
    "gif": ".gif",
    "bmp": ".bmp",
    "tiff": ".tiff",
    "pdf": ".pdf",
    "ico": ".ico",
    "json": ".json",
}

EXT_FMT = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".avif": "AVIF",
    ".gif": "GIF",
    ".bmp": "BMP",
    ".tif": "TIFF",
    ".tiff": "TIFF",
    ".ico": "ICO",
}

MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".ico": "image/x-icon",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".zip": "application/zip",
}

QUALITY_PRESETS = {
    "high": 90,
    "balanced": 75,
    "small": 55,
}


def mime_for_ext(ext: str) -> str:
    return MIME_BY_EXT.get(ext.lower(), "application/octet-stream")


def open_image(path: Path) -> Image.Image:
    """Open and auto-orient an image; raise AppError on failure."""
    try:
        img = Image.open(path)
        img.load()
        return ImageOps.exif_transpose(img)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppError("UNSUPPORTED_FORMAT", "Could not read this image file.") from exc


def flatten_rgb(img: Image.Image, bg: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """Convert to RGB, compositing alpha onto a solid background."""
    if img.mode in {"RGBA", "LA"} or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, bg)
        base.paste(rgba, mask=rgba.split()[-1])
        return base
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def ensure_mode_for_fmt(img: Image.Image, fmt: str) -> Image.Image:
    """Prepare image mode for the target save format."""
    key = fmt.lower()
    if key in {"jpg", "jpeg"}:
        return flatten_rgb(img)
    if key == "png":
        if img.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
            return img.convert("RGBA")
        return img
    if key in {"webp", "avif"}:
        if img.mode not in {"RGB", "RGBA"}:
            return img.convert("RGBA" if "A" in img.getbands() else "RGB")
        return img
    if key == "gif":
        return img.convert("P", palette=Image.Palette.ADAPTIVE)
    return img


def save_image(
    img: Image.Image,
    path: Path,
    *,
    fmt: str | None = None,
    quality: int | None = None,
    optimize: bool = True,
    strip_exif: bool = True,
) -> Path:
    """Save image to path with sensible defaults."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    pil_fmt = (fmt or EXT_FMT.get(ext, "PNG")).upper()
    if pil_fmt == "JPG":
        pil_fmt = "JPEG"

    prepared = ensure_mode_for_fmt(img, pil_fmt.lower() if pil_fmt != "JPEG" else "jpg")
    kwargs: dict = {}
    if pil_fmt in {"JPEG", "WEBP", "AVIF"} and quality is not None:
        kwargs["quality"] = max(1, min(100, int(quality)))
    if pil_fmt in {"PNG", "JPEG"} and optimize:
        kwargs["optimize"] = True
    if pil_fmt == "JPEG":
        kwargs.setdefault("quality", 85)
        kwargs["progressive"] = True
    if pil_fmt == "WEBP":
        kwargs.setdefault("quality", 85)
        kwargs["method"] = 4
    if pil_fmt == "AVIF":
        kwargs.setdefault("quality", 80)

    # Drop EXIF by not copying info
    save_img = prepared.copy() if strip_exif else prepared
    if strip_exif:
        save_img.info = {}

    try:
        save_img.save(path, format=pil_fmt, **kwargs)
    except Exception as exc:  # noqa: BLE001
        raise AppError("INTERNAL_ERROR", f"Failed to save image as {pil_fmt}.") from exc
    return path


def save_bytes(img: Image.Image, fmt: str, *, quality: int | None = None) -> bytes:
    """Encode image to in-memory bytes."""
    buf = io.BytesIO()
    ext = FMT_EXT.get(fmt.lower(), ".png")
    pil_fmt = EXT_FMT.get(ext, "PNG")
    prepared = ensure_mode_for_fmt(img, fmt.lower())
    kwargs: dict = {}
    if pil_fmt in {"JPEG", "WEBP", "AVIF"} and quality is not None:
        kwargs["quality"] = max(1, min(100, int(quality)))
    if pil_fmt == "JPEG":
        kwargs.setdefault("quality", 85)
        kwargs["optimize"] = True
        kwargs["progressive"] = True
    if pil_fmt == "PNG":
        kwargs["optimize"] = True
    if pil_fmt == "WEBP":
        kwargs.setdefault("quality", 85)
        kwargs["method"] = 4
    prepared.info = {}
    prepared.save(buf, format=pil_fmt, **kwargs)
    return buf.getvalue()


def detect_fmt(path: Path) -> str:
    """Return short format key from path extension."""
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "jpg"
    if ext == ".png":
        return "png"
    if ext == ".webp":
        return "webp"
    if ext == ".avif":
        return "avif"
    if ext == ".gif":
        return "gif"
    if ext in {".tif", ".tiff"}:
        return "tiff"
    if ext == ".bmp":
        return "bmp"
    if ext == ".pdf":
        return "pdf"
    return "png"
