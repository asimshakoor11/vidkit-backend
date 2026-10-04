"""Local storage path helpers and filesystem cleanup."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def ensure_storage_dirs(settings: Settings | None = None) -> None:
    """Create storage directory tree if missing."""
    cfg = settings or get_settings()
    for path in (cfg.storage_dir, cfg.uploads_dir, cfg.outputs_dir, cfg.tmp_dir):
        path.mkdir(parents=True, exist_ok=True)


def job_upload_dir(job_id: str, settings: Settings | None = None) -> Path:
    """Return (and create) the upload directory for a job."""
    cfg = settings or get_settings()
    path = cfg.uploads_dir / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_output_dir(job_id: str, settings: Settings | None = None) -> Path:
    """Return (and create) the output directory for a job."""
    cfg = settings or get_settings()
    path = cfg.outputs_dir / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_stored_path(stored_path: str, settings: Settings | None = None) -> Path:
    """Resolve a relative stored_path against STORAGE_DIR."""
    cfg = settings or get_settings()
    path = Path(stored_path)
    if path.is_absolute():
        return path
    return (cfg.storage_dir / path).resolve()


def relative_storage_path(absolute: Path, settings: Settings | None = None) -> str:
    """Store paths relative to STORAGE_DIR when possible."""
    cfg = settings or get_settings()
    try:
        return str(absolute.resolve().relative_to(cfg.storage_dir.resolve()))
    except ValueError:
        return str(absolute)


def delete_job_dirs(job_id: str, settings: Settings | None = None) -> None:
    """Remove upload and output directories for a job."""
    cfg = settings or get_settings()
    for path in (cfg.uploads_dir / job_id, cfg.outputs_dir / job_id):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            logger.info("deleted_job_dir", path=str(path))
