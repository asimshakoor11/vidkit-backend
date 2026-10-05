"""EXIF metadata view and strip."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import ExifTags

from app.core.errors import AppError
from app.services.image.io import detect_fmt, open_image, save_image

MODES = {"view", "strip"}


def process_exif(
    input_path: Path,
    output_dir: Path,
    *,
    mode: str = "strip",
    progress_callback=None,
) -> Path:
    if mode not in MODES:
        raise AppError("UNSUPPORTED_FORMAT", "Mode must be view or strip.")

    if progress_callback:
        progress_callback(15, "reading")

    img = open_image(input_path)
    data = _read_exif(img)

    output_dir.mkdir(parents=True, exist_ok=True)

    if mode == "view":
        out = output_dir / f"{input_path.stem}_exif.json"
        out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        if progress_callback:
            progress_callback(100, "done")
        return out

    fmt = detect_fmt(input_path)
    if fmt not in {"jpg", "png", "webp", "avif", "tiff"}:
        fmt = "jpg"
    out = output_dir / f"{input_path.stem}_clean.{fmt if fmt != 'jpg' else 'jpg'}"
    save_image(img, out, fmt=fmt, quality=95, strip_exif=True)

    if progress_callback:
        progress_callback(100, "done")
    return out


def _read_exif(img) -> dict:
    result: dict = {
        "format": img.format,
        "mode": img.mode,
        "width": img.width,
        "height": img.height,
        "exif": {},
    }
    try:
        raw = img.getexif()
    except Exception:  # noqa: BLE001
        return result
    if not raw:
        return result
    for tag_id, value in raw.items():
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        try:
            result["exif"][name] = _safe(value)
        except Exception:  # noqa: BLE001
            result["exif"][name] = str(value)
    return result


def _safe(value):
    if isinstance(value, bytes):
        return value.hex()[:64]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)
