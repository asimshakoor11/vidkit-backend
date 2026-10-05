"""Text or image watermark overlay."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.core.errors import AppError
from app.services.image.io import detect_fmt, open_image, save_image

POSITIONS = {
    "tl",
    "tr",
    "bl",
    "br",
    "center",
}


def add_watermark(
    input_path: Path,
    output_dir: Path,
    *,
    text: str | None = None,
    mark_path: Path | None = None,
    position: str = "br",
    opacity: float = 0.4,
    scale: float = 0.2,
    progress_callback=None,
) -> Path:
    if position not in POSITIONS:
        raise AppError("UNSUPPORTED_FORMAT", "Invalid watermark position.")
    if not text and not mark_path:
        raise AppError("UNSUPPORTED_FORMAT", "Provide watermark text or an overlay image.")
    opacity = max(0.05, min(1.0, opacity))
    scale = max(0.05, min(1.0, scale))

    if progress_callback:
        progress_callback(10, "opening")

    base = open_image(input_path).convert("RGBA")

    if mark_path:
        mark = open_image(mark_path).convert("RGBA")
        mw = max(1, int(base.width * scale))
        ratio = mw / mark.width
        mh = max(1, int(mark.height * ratio))
        mark = mark.resize((mw, mh), Image.Resampling.LANCZOS)
        if opacity < 1:
            alpha = mark.split()[-1].point(lambda p: int(p * opacity))
            mark.putalpha(alpha)
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        x, y = _pos(base.size, mark.size, position)
        overlay.paste(mark, (x, y), mark)
        base = Image.alpha_composite(base, overlay)
    else:
        assert text is not None
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font_size = max(12, int(base.width * 0.04))
        font = _font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = _pos(base.size, (tw, th), position, pad=16)
        fill = (255, 255, 255, int(255 * opacity))
        stroke = (0, 0, 0, int(200 * opacity))
        draw.text((x, y), text, font=font, fill=fill, stroke_width=2, stroke_fill=stroke)
        base = Image.alpha_composite(base, overlay)

    if progress_callback:
        progress_callback(70, "watermarking")

    fmt = detect_fmt(input_path)
    if fmt not in {"jpg", "png", "webp"}:
        fmt = "png"
    # Keep alpha for png/webp
    out_img = base if fmt != "jpg" else base.convert("RGB")

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{input_path.stem}_wm.{fmt if fmt != 'jpg' else 'jpg'}"
    save_image(out_img, out, fmt=fmt, quality=90)

    if progress_callback:
        progress_callback(100, "done")
    return out


def _pos(
    canvas: tuple[int, int],
    size: tuple[int, int],
    position: str,
    pad: int = 12,
) -> tuple[int, int]:
    cw, ch = canvas
    sw, sh = size
    if position == "tl":
        return pad, pad
    if position == "tr":
        return cw - sw - pad, pad
    if position == "bl":
        return pad, ch - sh - pad
    if position == "br":
        return cw - sw - pad, ch - sh - pad
    return (cw - sw) // 2, (ch - sh) // 2


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for name in (
        "arial.ttf",
        "Arial.ttf",
        "DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()
