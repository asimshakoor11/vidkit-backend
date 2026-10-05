"""Image format conversion."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.image.io import FMT_EXT, open_image, save_image

ALLOWED = {"jpg", "png", "webp", "avif"}


def convert_image(
    input_path: Path,
    output_dir: Path,
    fmt: str,
    progress_callback=None,
) -> Path:
    key = fmt.lower()
    if key == "jpeg":
        key = "jpg"
    if key not in ALLOWED:
        raise AppError("UNSUPPORTED_FORMAT", "Format must be jpg, png, webp, or avif.")

    if progress_callback:
        progress_callback(15, "opening")

    img = open_image(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{input_path.stem}{FMT_EXT[key]}"

    if progress_callback:
        progress_callback(60, "converting")

    save_image(img, out, fmt=key, quality=90)

    if progress_callback:
        progress_callback(100, "done")
    return out
