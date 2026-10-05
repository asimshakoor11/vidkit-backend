"""Image compression presets and target-KB sizing."""

from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError
from app.services.image.io import (
    QUALITY_PRESETS,
    detect_fmt,
    open_image,
    save_bytes,
    save_image,
)


def compress_image(
    input_path: Path,
    output_dir: Path,
    preset: str,
    progress_callback=None,
) -> Path:
    """Compress keeping original format when possible."""
    if preset not in QUALITY_PRESETS:
        raise AppError("UNSUPPORTED_FORMAT", "Preset must be high, balanced, or small.")

    if progress_callback:
        progress_callback(10, "opening")

    img = open_image(input_path)
    fmt = detect_fmt(input_path)
    if fmt not in {"jpg", "png", "webp", "avif"}:
        fmt = "jpg"

    quality = QUALITY_PRESETS[preset]
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{input_path.stem}_compressed.{fmt if fmt != 'jpg' else 'jpg'}"

    if progress_callback:
        progress_callback(50, "compressing")

    if fmt == "png":
        save_image(img, out, fmt="png", optimize=True)
    else:
        save_image(img, out, fmt=fmt, quality=quality)

    if progress_callback:
        progress_callback(100, "done")
    return out


def compress_to_kb(
    input_path: Path,
    output_dir: Path,
    target_kb: int,
    progress_callback=None,
) -> Path:
    """Binary-search quality until file size is at or under target_kb."""
    if target_kb < 1:
        raise AppError("UNSUPPORTED_FORMAT", "Target size must be at least 1 KB.")

    if progress_callback:
        progress_callback(5, "opening")

    img = open_image(input_path)
    fmt = detect_fmt(input_path)
    if fmt not in {"jpg", "webp", "avif"}:
        # PNG target size via convert-to-JPEG path for predictable quality control
        fmt = "jpg"

    target_bytes = target_kb * 1024
    lo, hi = 5, 95
    best: bytes | None = None
    best_q = 50

    steps = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        data = save_bytes(img, fmt, quality=mid)
        steps += 1
        if progress_callback:
            progress_callback(10 + min(80, steps * 10), "compressing")
        if len(data) <= target_bytes:
            best = data
            best_q = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if best is None:
        # Best effort: lowest quality
        best = save_bytes(img, fmt, quality=5)
        if len(best) > target_bytes:
            raise AppError(
                "UNSUPPORTED_FORMAT",
                f"Could not reach {target_kb} KB even at lowest quality "
                f"({max(1, len(best) // 1024)} KB).",
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if fmt == "jpg" else fmt
    out = output_dir / f"{input_path.stem}_{target_kb}kb.{ext}"
    out.write_bytes(best)

    if progress_callback:
        progress_callback(100, "done")
    _ = best_q
    return out
