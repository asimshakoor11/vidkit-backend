"""Job status, SSE, cancel, and ZIP routes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.database import SessionLocal, get_db
from app.core.errors import AppError
from app.core.security import sanitize_filename
from app.schemas.job import JobStatusResponse
from app.services.job_service import get_job_or_404, job_to_response, update_job_progress
from app.services.storage import delete_job_dirs, job_output_dir, resolve_stored_path
from app.services.zip_service import build_zip
from app.workers.runner import runner

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    """Return job status, progress, and outputs."""
    job = get_job_or_404(db, job_id)
    return job_to_response(job)


@router.get("/{job_id}/events")
async def job_events(job_id: str) -> EventSourceResponse:
    """SSE stream of job progress updates."""

    async def event_generator():  # type: ignore[no-untyped-def]
        last_payload = None
        while True:
            db = SessionLocal()
            try:
                job = get_job_or_404(db, job_id)
                payload = job_to_response(job).model_dump(mode="json")
            except AppError as exc:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": {"code": exc.code, "message": exc.message}}),
                }
                break
            finally:
                db.close()

            serialized = json.dumps(payload)
            if serialized != last_payload:
                last_payload = serialized
                yield {"event": "progress", "data": serialized}

            if payload["status"] in {"completed", "failed", "cancelled", "expired"}:
                yield {"event": "done", "data": serialized}
                break

            await asyncio.sleep(1.0)

    return EventSourceResponse(event_generator())


@router.delete("/{job_id}")
async def cancel_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    """Cancel a job and delete its files."""
    job = get_job_or_404(db, job_id)
    if job.status in {"completed", "failed", "cancelled", "expired"}:
        delete_job_dirs(job_id)
        update_job_progress(db, job_id, status="cancelled", stage="cancelled")
        return {"status": "cancelled", "job_id": job_id}

    await runner.cancel(job_id)
    delete_job_dirs(job_id)
    update_job_progress(db, job_id, status="cancelled", stage="cancelled", progress=0)
    return {"status": "cancelled", "job_id": job_id}


@router.get("/{job_id}/zip")
async def download_zip(job_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    """Stream all output parts as a ZIP archive."""
    job = get_job_or_404(db, job_id)
    if job.status != "completed":
        raise AppError("JOB_NOT_FOUND", "Job outputs are not ready yet.", status_code=404)

    outputs = [f for f in job.files if f.role == "output"]
    if not outputs:
        raise AppError("JOB_NOT_FOUND", "No output files for this job.", status_code=404)

    zip_path = job_output_dir(job_id) / f"{job_id}.zip"
    entries: list[tuple[str, Path]] = []
    for f in sorted(outputs, key=lambda x: (x.part_index is None, x.part_index or 0)):
        path = resolve_stored_path(f.stored_path)
        entries.append((sanitize_filename(f.original_name), path))

    build_zip(zip_path, entries)

    def iterfile():  # type: ignore[no-untyped-def]
        with zip_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    headers = {
        "Content-Disposition": f'attachment; filename="{job_id}.zip"',
    }
    return StreamingResponse(iterfile(), media_type="application/zip", headers=headers)
