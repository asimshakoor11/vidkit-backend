"""Split a PDF into pages or custom ranges."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfWriter

from app.core.errors import AppError
from app.services.pdf.io import ProgressCb, open_reader, out_name, write_writer

_RANGE_TOKEN = re.compile(r"^(\d+)(?:-(\d+))?$")


def parse_ranges(spec: str, page_count: int) -> list[list[int]]:
    """
    Parse range strings like '1-3,5,7-9' into 0-based page index groups.
    Each comma-separated token becomes one output file.
    """
    if not spec or not spec.strip():
        raise AppError("UNSUPPORTED_FORMAT", "Provide page ranges like 1-3,5,7-9.")

    groups: list[list[int]] = []
    for raw in spec.split(","):
        token = raw.strip().replace(" ", "")
        if not token:
            continue
        match = _RANGE_TOKEN.match(token)
        if not match:
            raise AppError("UNSUPPORTED_FORMAT", f"Invalid page range: {raw.strip()}")
        start = int(match.group(1))
        end = int(match.group(2) or match.group(1))
        if start < 1 or end < start or end > page_count:
            raise AppError(
                "UNSUPPORTED_FORMAT",
                f"Page range {token} is out of bounds (1–{page_count}).",
            )
        groups.append(list(range(start - 1, end)))

    if not groups:
        raise AppError("UNSUPPORTED_FORMAT", "Provide page ranges like 1-3,5,7-9.")
    return groups


def split_pdf(
    input_path: Path,
    output_dir: Path,
    *,
    mode: str = "each",
    ranges: str | None = None,
    progress_callback: ProgressCb = None,
) -> list[Path]:
    """Split PDF into one file per page or per range group."""
    def report(pct: float, stage: str) -> None:
        if progress_callback:
            progress_callback(pct, stage)

    report(5, "reading")
    reader = open_reader(input_path)
    total = len(reader.pages)
    if total < 1:
        raise AppError("UNSUPPORTED_FORMAT", "This PDF has no pages.")

    if mode == "each":
        groups = [[i] for i in range(total)]
    elif mode == "ranges":
        groups = parse_ranges(ranges or "", total)
    else:
        raise AppError("UNSUPPORTED_FORMAT", "Split mode must be each or ranges.")

    stem = input_path.stem
    outputs: list[Path] = []
    for g_index, indices in enumerate(groups, start=1):
        writer = PdfWriter()
        for i in indices:
            writer.add_page(reader.pages[i])
        label = f"p{g_index:02d}" if mode == "each" else f"part{g_index:02d}"
        out = output_dir / out_name(stem, label)
        write_writer(writer, out)
        outputs.append(out)
        report(5 + g_index / len(groups) * 90, "splitting")

    report(100, "done")
    return outputs
