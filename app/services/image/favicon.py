"""Generate favicon pack (PNG sizes + ICO) as a ZIP."""

from __future__ import annotations

import zipfile
from pathlib import Path

from PIL import Image

from app.services.image.io import open_image

SIZES = (16, 32, 48, 64, 180, 192, 512)


def make_favicon(
    input_path: Path,
    output_dir: Path,
    progress_callback=None,
) -> list[Path]:
    """Return list of generated files (pngs, ico, zip). Primary deliverable is the zip."""
    if progress_callback:
        progress_callback(10, "opening")

    img = open_image(input_path).convert("RGBA")
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    files: list[Path] = []

    # Square cover crop then resize
    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    square = img.crop((left, top, left + side, top + side))

    ico_images: list[Image.Image] = []
    for i, size in enumerate(SIZES):
        resized = square.resize((size, size), Image.Resampling.LANCZOS)
        path = output_dir / f"{stem}_{size}.png"
        resized.save(path, format="PNG", optimize=True)
        files.append(path)
        if size in {16, 32, 48}:
            ico_images.append(resized)
        if progress_callback:
            progress_callback(20 + int(60 * (i + 1) / len(SIZES)), "generating")

    ico_path = output_dir / "favicon.ico"
    if ico_images:
        ico_images[0].save(
            ico_path,
            format="ICO",
            sizes=[(im.width, im.height) for im in ico_images],
            append_images=ico_images[1:],
        )
        files.append(ico_path)

    zip_path = output_dir / f"{stem}_favicons.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
    files.append(zip_path)

    if progress_callback:
        progress_callback(100, "done")
    # Prefer zip as the main single-download; still register all files for multi-output UI
    return files
