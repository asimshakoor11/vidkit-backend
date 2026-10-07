"""APScheduler cleanup for expired jobs and short URLs."""

from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models.short_url import ShortUrl
from app.services.job_service import expire_jobs

logger = get_logger(__name__)

scheduler = AsyncIOScheduler()


def cleanup_expired_jobs() -> None:
    """Delete expired job files and mark jobs expired; purge expired short URLs."""
    db = SessionLocal()
    try:
        count = expire_jobs(db)
        if count:
            logger.info("expired_jobs", count=count)
        now = datetime.now(timezone.utc)
        result = db.execute(delete(ShortUrl).where(ShortUrl.expires_at < now))
        db.commit()
        deleted = result.rowcount or 0
        if deleted:
            logger.info("expired_short_urls", count=deleted)
    finally:
        db.close()


def start_cleanup_scheduler() -> None:
    """Start the periodic cleanup task (every 5 minutes)."""
    import os

    if os.environ.get("VIDKIT_DISABLE_SCHEDULER") == "1":
        logger.info("cleanup_scheduler_disabled")
        return
    if scheduler.running:
        return
    scheduler.add_job(
        cleanup_expired_jobs,
        trigger="interval",
        minutes=5,
        id="expire_jobs",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("cleanup_scheduler_started")


def stop_cleanup_scheduler() -> None:
    """Shut down the cleanup scheduler."""
    import os

    if os.environ.get("VIDKIT_DISABLE_SCHEDULER") == "1":
        return
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("cleanup_scheduler_stopped")
