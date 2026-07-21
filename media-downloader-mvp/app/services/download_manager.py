from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import HTTPException, status

from app.models.schemas import DownloadRequest
from app.services.media_service import DownloadCanceledError, MediaService


TERMINAL_STATUSES = {"completed", "failed", "canceled"}


@dataclass
class DownloadJob:
    job_id: str
    request: DownloadRequest
    status: str = "queued"
    percentage: float = 0
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    speed: float | None = None
    eta: float | None = None
    filename: str | None = None
    error: str | None = None
    file_path: Path | None = None
    version: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "percentage": round(self.percentage, 1),
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "speed": self.speed,
            "eta": self.eta,
            "filename": self.filename,
            "error": self.error,
        }


class DownloadManager:
    def __init__(self, service: MediaService, ttl_seconds: int, timeout_seconds: int) -> None:
        self.service = service
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._jobs: dict[str, DownloadJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._expiry_tasks: dict[str, asyncio.Task[None]] = {}

    def create(self, request: DownloadRequest) -> DownloadJob:
        self._prune_expired()
        job = DownloadJob(job_id=uuid.uuid4().hex, request=request.model_copy(deep=True))
        self._jobs[job.job_id] = job
        self._tasks[job.job_id] = asyncio.create_task(self._run(job))
        return job

    def get(self, job_id: str) -> DownloadJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Download job not found.")
        return job

    def retry(self, job_id: str) -> DownloadJob:
        job = self.get(job_id)
        if job.status not in {"failed", "canceled"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only failed or canceled downloads can be retried.",
            )
        return self.create(job.request)

    async def cancel(self, job_id: str) -> DownloadJob:
        job = self.get(job_id)
        if job.status in TERMINAL_STATUSES:
            return job
        job.cancel_event.set()
        task = self._tasks.get(job_id)
        if task and job.status == "queued":
            task.cancel()
        if task:
            try:
                await task
            except asyncio.CancelledError:
                pass
        if job.status not in TERMINAL_STATUSES:
            await self._update(job, status="canceled", speed=None, eta=None)
            self._ensure_expiry(job)
        self.service.cleanup_job(job_id)
        job.file_path = None
        return job

    def completed_file(self, job_id: str) -> Path:
        job = self.get(job_id)
        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The download is not ready.",
            )
        if job.file_path is None or not job.file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="The downloaded file is no longer available.",
            )
        return job.file_path

    def remove_file(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job or not job.file_path:
            return
        self.service.cleanup_job(job_id)
        job.file_path = None
        job.updated_at = time.time()

    def active_job_ids(self) -> set[str]:
        return {
            job_id
            for job_id, job in self._jobs.items()
            if job.status not in TERMINAL_STATUSES
        }

    async def events(self, job_id: str) -> AsyncIterator[str]:
        job = self.get(job_id)
        observed_version = -1
        while True:
            if job.version != observed_version:
                observed_version = job.version
                yield f"data: {json.dumps(job.snapshot(), separators=(',', ':'))}\n\n"
                if job.status in TERMINAL_STATUSES:
                    return

            try:
                async with job.condition:
                    await asyncio.wait_for(
                        job.condition.wait_for(lambda: job.version != observed_version),
                        timeout=15,
                    )
            except TimeoutError:
                yield ": keep-alive\n\n"

    async def _run(self, job: DownloadJob) -> None:
        loop = asyncio.get_running_loop()

        def on_start() -> None:
            if job.cancel_event.is_set():
                raise DownloadCanceledError()
            self._apply_update(job, status="preparing")

        def on_progress(update: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(partial(self._apply_update, job, **update))

        try:
            download_task = asyncio.create_task(
                self.service.download(
                    str(job.request.url),
                    job.request.mode,
                    job.request.format_id,
                    progress_callback=on_progress,
                    cancel_event=job.cancel_event,
                    on_start=on_start,
                    job_id=job.job_id,
                )
            )
            done, _ = await asyncio.wait({download_task}, timeout=self.timeout_seconds)
            if not done:
                job.cancel_event.set()
                try:
                    await download_task
                except (DownloadCanceledError, HTTPException):
                    pass
                finally:
                    self.service.cleanup_job(job.job_id)
                raise TimeoutError("Download job timed out.")
            file_path = download_task.result()
            if job.cancel_event.is_set():
                self.service.cleanup_job(job.job_id)
                return
            job.file_path = file_path
            await self._update(
                job,
                status="completed",
                percentage=100,
                filename=file_path.name,
                speed=None,
                eta=0,
            )
        except DownloadCanceledError:
            await self._update(job, status="canceled", speed=None, eta=None)
        except TimeoutError:
            await self._update(
                job,
                status="failed",
                error="The download timed out.",
                speed=None,
                eta=None,
            )
        except HTTPException as exc:
            await self._update(job, status="failed", error=str(exc.detail), speed=None, eta=None)
        except Exception:
            await self._update(
                job,
                status="failed",
                error="The download failed. Please try again.",
                speed=None,
                eta=None,
            )
        finally:
            self._tasks.pop(job.job_id, None)
            self._ensure_expiry(job)

    def _ensure_expiry(self, job: DownloadJob) -> None:
        if job.status in TERMINAL_STATUSES and job.job_id not in self._expiry_tasks:
            self._expiry_tasks[job.job_id] = asyncio.create_task(self._expire(job.job_id))

    async def _expire(self, job_id: str) -> None:
        try:
            await asyncio.sleep(self.ttl_seconds)
            job = self._jobs.pop(job_id, None)
            if job and job.file_path:
                self.service.cleanup_job(job_id)
        finally:
            self._expiry_tasks.pop(job_id, None)

    def _apply_update(self, job: DownloadJob, **changes: Any) -> None:
        if job.status == "canceled" and changes.get("status") != "canceled":
            return
        for key, value in changes.items():
            if hasattr(job, key):
                setattr(job, key, value)
        job.updated_at = time.time()
        job.version += 1

        async def notify() -> None:
            async with job.condition:
                job.condition.notify_all()

        asyncio.create_task(notify())

    async def _update(self, job: DownloadJob, **changes: Any) -> None:
        self._apply_update(job, **changes)
        await asyncio.sleep(0)

    def _prune_expired(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in TERMINAL_STATUSES and job.updated_at < cutoff
        ]
        for job_id in expired:
            job = self._jobs.pop(job_id)
            if job.file_path:
                self.service.cleanup_job(job_id)
