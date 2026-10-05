"""Classic top/bottom meme text generator."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.core.errors import AppError
from app.services.image.io import open_image, save_image


def make_meme(
    input_path: Path,
    output_dir: Path,
    *,
    top: str = "",
    bottom: str = "",
    font_size: int | None = None,
    progress_callback=None,
) -> Path:
    if not top.strip() and not bottom.strip():
        raise AppError("UNSUPPORTED_FORMAT", "Enter top and/or bottom meme text.")

    if progress_callback:
        progress_callback(10, "opening")

    img = open_image(input_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    size = font_size or max(18, img.width // 12)
    font = _impact(size)

    if top.strip():
        _draw_centered(draw, top.strip().upper(), font, img.width, y_ratio=0.04, img_h=img.height)
    if bottom.strip():
        _draw_centered(
            draw,
            bottom.strip().upper(),
            font,
            img.width,
            y_ratio=0.88,
            img_h=img.height,
        )

    if progress_callback:
        progress_callback(70, "drawing")

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{input_path.stem}_meme.jpg"
    save_image(img, out, fmt="jpg", quality=92)

    if progress_callback:
        progress_callback(100, "done")
    return out


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    width: int,
    *,
    y_ratio: float,
    img_h: int,
) -> None:
    # Wrap roughly by character count
    fsize = int(getattr(font, "size", 24) or 24)
    max_chars = max(8, width // max(1, fsize // 2))
    lines = _wrap(text, max_chars)
    y = int(img_h * y_ratio)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (width - tw) // 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=max(2, fsize // 18),
            stroke_fill=(0, 0, 0),
        )
        y += th + 4


def _wrap(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= max_chars:
            cur = f"{cur} {w}"
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _impact(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for name in (
        "impact.ttf",
        "Impact.ttf",
        "C:\\Windows\\Fonts\\impact.ttf",
        "arialbd.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()
