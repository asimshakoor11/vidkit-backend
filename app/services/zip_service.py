"""On-demand ZIP packaging for job outputs."""

from __future__ import annotations

import zipfile
from collections.abc import Iterable
from pathlib import Path


def build_zip(zip_path: Path, files: Iterable[tuple[str, Path]]) -> Path:
    """
    Create a ZIP archive using ZIP_STORED (videos are already compressed).

    files: iterable of (archive_name, absolute_path)
    """
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for arcname, path in files:
            if path.is_file():
                zf.write(path, arcname=arcname)
    return zip_path
