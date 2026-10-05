"""Image resize and crop."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.core.errors import AppError
from app.services.image.io import detect_fmt, open_image, save_image

MODES = {"fit", "fill", "exact"}


def resize_image(
    input_path: Path,
    output_dir: Path,
    *,
    width: int | None = None,
    height: int | None = None,
    mode: str = "fit",
    crop_x: int | None = None,
    crop_y: int | None = None,
    crop_w: int | None = None,
    crop_h: int | None = None,
    progress_callback=None,
) -> Path:
    if mode not in MODES:
        raise AppError("UNSUPPORTED_FORMAT", "Mode must be fit, fill, or exact.")

    if progress_callback:
        progress_callback(10, "opening")

    img = open_image(input_path)

    # Optional crop first
    if None not in (crop_x, crop_y, crop_w, crop_h):
        assert crop_x is not None and crop_y is not None
        assert crop_w is not None and crop_h is not None
        if crop_w < 1 or crop_h < 1:
            raise AppError("INVALID_RANGE", "Crop size must be positive.")
        box = (
            max(0, crop_x),
            max(0, crop_y),
            min(img.width, crop_x + crop_w),
            min(img.height, crop_y + crop_h),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            raise AppError("INVALID_RANGE", "Crop box is outside the image.")
        img = img.crop(box)

    if width or height:
        tw = width or img.width
        th = height or img.height
        if tw < 1 or th < 1:
            raise AppError("UNSUPPORTED_FORMAT", "Width and height must be positive.")

        if mode == "exact":
            img = img.resize((tw, th), Image.Resampling.LANCZOS)
        elif mode == "fill":
            img = _cover(img, tw, th)
        else:
            img = _fit(img, tw, th)

    if progress_callback:
        progress_callback(70, "resizing")

    fmt = detect_fmt(input_path)
    if fmt not in {"jpg", "png", "webp", "avif"}:
        fmt = "png"

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{input_path.stem}_{img.width}x{img.height}.{fmt if fmt != 'jpg' else 'jpg'}"
    save_image(img, out, fmt=fmt, quality=90)

    if progress_callback:
        progress_callback(100, "done")
    return out


def _fit(img: Image.Image, tw: int, th: int) -> Image.Image:
    copy = img.copy()
    copy.thumbnail((tw, th), Image.Resampling.LANCZOS)
    return copy


def _cover(img: Image.Image, tw: int, th: int) -> Image.Image:
    src_ratio = img.width / img.height
    dst_ratio = tw / th
    if src_ratio > dst_ratio:
        # wider — match height
        new_h = th
        new_w = int(th * src_ratio)
    else:
        new_w = tw
        new_h = int(tw / src_ratio)
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - tw) // 2
    top = (new_h - th) // 2
    return resized.crop((left, top, left + tw, top + th))
