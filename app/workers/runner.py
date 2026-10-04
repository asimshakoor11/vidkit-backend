"""JobRunner interface and in-process asyncio worker pool."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

JobCoroutineFactory = Callable[[], Awaitable[Any]]


class JobRunner(ABC):
    """Abstract background job runner (swappable for Celery later)."""

    @abstractmethod
    async def submit(self, job_id: str, factory: JobCoroutineFactory) -> None:
        """Enqueue work for job_id."""

    @abstractmethod
    async def cancel(self, job_id: str) -> bool:
        """Cancel a running or queued job. Returns True if found."""

    @abstractmethod
    def is_active(self, job_id: str) -> bool:
        """Return True if the job is queued or running."""


class InProcessJobRunner(JobRunner):
    """Bounded asyncio worker pool running job coroutines in-process."""

    def __init__(self, max_workers: int | None = None) -> None:
        settings = get_settings()
        self._max_workers = max_workers or settings.max_concurrent_jobs
        self._queue: asyncio.Queue[tuple[str, JobCoroutineFactory] | None] = asyncio.Queue()
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._cancel_flags: set[str] = set()
        self._workers: list[asyncio.Task[Any]] = []
        self._started = False
        # Optional external cancel hooks (e.g. kill ffmpeg)
        self._cancel_hooks: dict[str, Callable[[], None]] = {}

    def register_cancel_hook(self, job_id: str, hook: Callable[[], None]) -> None:
        """Register a side-effect to run when a job is cancelled."""
        self._cancel_hooks[job_id] = hook

    def clear_cancel_hook(self, job_id: str) -> None:
        self._cancel_hooks.pop(job_id, None)

    async def start(self) -> None:
        """Start worker tasks."""
        if self._started:
            return
        self._started = True
        for index in range(self._max_workers):
            self._workers.append(asyncio.create_task(self._worker_loop(index)))
        logger.info("job_runner_started", workers=self._max_workers)

    async def stop(self) -> None:
        """Stop workers and cancel active tasks."""
        for _ in self._workers:
            await self._queue.put(None)
        for worker in self._workers:
            await worker
        self._workers.clear()
        for job_id, task in list(self._tasks.items()):
            task.cancel()
            self._cancel_flags.add(job_id)
        self._tasks.clear()
        self._started = False

    async def submit(self, job_id: str, factory: JobCoroutineFactory) -> None:
        if not self._started:
            await self.start()
        self._cancel_flags.discard(job_id)
        await self._queue.put((job_id, factory))
        logger.info("job_queued", job_id=job_id)

    async def cancel(self, job_id: str) -> bool:
        self._cancel_flags.add(job_id)
        hook = self._cancel_hooks.pop(job_id, None)
        if hook:
            try:
                hook()
            except Exception:  # noqa: BLE001
                logger.exception("cancel_hook_failed", job_id=job_id)
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True
        return job_id in self._cancel_flags

    def is_active(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        return bool(task and not task.done())

    def is_cancelled(self, job_id: str) -> bool:
        return job_id in self._cancel_flags

    async def _worker_loop(self, worker_index: int) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            job_id, factory = item
            if job_id in self._cancel_flags:
                self._queue.task_done()
                continue
            task = asyncio.create_task(factory())
            self._tasks[job_id] = task
            try:
                await task
            except asyncio.CancelledError:
                logger.info("job_cancelled_task", job_id=job_id, worker=worker_index)
            except Exception:  # noqa: BLE001
                logger.exception("job_worker_error", job_id=job_id, worker=worker_index)
            finally:
                self._tasks.pop(job_id, None)
                self.clear_cancel_hook(job_id)
                self._queue.task_done()


# Process-wide singleton
runner = InProcessJobRunner()
