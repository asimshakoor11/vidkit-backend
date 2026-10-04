"""File download routes with Range support."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import sanitize_filename
from app.services.job_service import get_file_or_404

router = APIRouter(prefix="/api/files", tags=["files"])


def _file_iterator(path: Path, start: int, end: int, chunk_size: int = 1024 * 1024):
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = handle.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Stream a single output file; supports HTTP Range requests."""
    row, path = get_file_or_404(db, file_id)
    file_size = path.stat().st_size
    content_type = row.mime_type or mimetypes.guess_type(row.original_name)[0] or "application/octet-stream"
    filename = sanitize_filename(row.original_name)

    range_header = request.headers.get("range")
    if range_header:
        # Expected form: bytes=START-END
        try:
            units, _, rng = range_header.partition("=")
            if units.strip() != "bytes":
                raise ValueError("unsupported unit")
            start_s, _, end_s = rng.partition("-")
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else file_size - 1
            if start < 0 or end >= file_size or start > end:
                raise ValueError("invalid range")
        except ValueError as exc:
            raise AppError("INVALID_URL", "Invalid Range header.") from exc

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        return StreamingResponse(
            _file_iterator(path, start, end),
            status_code=206,
            media_type=content_type,
            headers=headers,
        )

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    if file_size == 0:
        return Response(
            content=b"",
            media_type=content_type,
            headers=headers,
        )
    return StreamingResponse(
        _file_iterator(path, 0, file_size - 1),
        media_type=content_type,
        headers=headers,
    )
