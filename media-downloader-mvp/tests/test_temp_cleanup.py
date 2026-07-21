from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.core.config import Settings
from app.models.schemas import DownloadRequest
from app.services.download_manager import DownloadManager
from app.services.media_service import MediaService
from app.services.temp_storage import TemporaryJobStorage


class FakeYoutubeDL:
    def __init__(self, options: dict, behavior: str) -> None:
        self.options = options
        self.behavior = behavior

    def __enter__(self) -> FakeYoutubeDL:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def extract_info(self, _: str, download: bool) -> dict:
        if self.behavior == "failure":
            raise RuntimeError("simulated extractor failure")

        if self.behavior == "wait":
            hook = self.options["progress_hooks"][0]
            while True:
                hook(
                    {
                        "status": "downloading",
                        "downloaded_bytes": 1,
                        "total_bytes": 10,
                        "speed": 1,
                        "eta": 9,
                    }
                )
                time.sleep(0.005)

        if download:
            output = self.options["outtmpl"].replace("%(id)s", "media").replace("%(ext)s", "mp4")
            Path(output).write_bytes(b"valid-media")

        return {
            "id": "media",
            "title": "Test media",
            "duration": 1,
            "formats": [],
        }


class TemporaryCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "jobs"
        self.settings = Settings(
            temp_root=self.root,
            temp_file_max_age_seconds=60,
            download_timeout_seconds=1,
            max_concurrent_downloads=1,
        )
        self.service = MediaService(self.settings)
        self.managers: list[DownloadManager] = []

    async def asyncTearDown(self) -> None:
        for manager in self.managers:
            tasks = list(manager._expiry_tasks.values())
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        self.temporary_directory.cleanup()

    def fake_downloader(self, behavior: str):
        return patch(
            "app.services.media_service.yt_dlp.YoutubeDL",
            side_effect=lambda options: FakeYoutubeDL(options, behavior),
        )

    async def wait_for_terminal(self, job) -> None:
        for _ in range(200):
            if job.status in {"completed", "failed", "canceled"}:
                return
            await asyncio.sleep(0.005)
        self.fail("download job did not reach a terminal state")

    async def test_completed_file_is_retained_until_delivery_cleanup(self) -> None:
        job_id = uuid.uuid4().hex
        with self.fake_downloader("success"):
            path = await self.service.download(
                "https://example.com/media",
                "video",
                None,
                job_id=job_id,
            )

        self.assertTrue(path.is_file(), "completed file was deleted before response delivery")
        self.service.cleanup_job(job_id)
        self.assertFalse((self.root / job_id).exists())

    async def test_failure_removes_job_directory(self) -> None:
        job_id = uuid.uuid4().hex
        with self.fake_downloader("failure"), self.assertRaises(HTTPException):
            await self.service.download(
                "https://example.com/media",
                "video",
                None,
                job_id=job_id,
            )
        self.assertFalse((self.root / job_id).exists())

    async def test_cancellation_waits_for_worker_and_removes_directory(self) -> None:
        manager = DownloadManager(self.service, ttl_seconds=300, timeout_seconds=2)
        self.managers.append(manager)
        with self.fake_downloader("wait"):
            job = manager.create(DownloadRequest(url="https://example.com/media"))
            for _ in range(100):
                if job.status == "downloading":
                    break
                await asyncio.sleep(0.005)
            await manager.cancel(job.job_id)

        self.assertEqual(job.status, "canceled")
        self.assertNotIn(job.job_id, manager._tasks)
        self.assertFalse((self.root / job.job_id).exists())

    async def test_timeout_waits_for_worker_and_removes_directory(self) -> None:
        manager = DownloadManager(self.service, ttl_seconds=300, timeout_seconds=0.03)
        self.managers.append(manager)
        with self.fake_downloader("wait"):
            job = manager.create(DownloadRequest(url="https://example.com/media"))
            await self.wait_for_terminal(job)

        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error, "The download timed out.")
        self.assertFalse((self.root / job.job_id).exists())

    def test_stale_job_directory_is_removed(self) -> None:
        storage = TemporaryJobStorage(self.root, max_age_seconds=60)
        job_id = uuid.uuid4().hex
        directory = storage.create_job_dir(job_id)
        old_time = time.time() - 120
        os.utime(directory, (old_time, old_time))

        self.assertEqual(storage.cleanup_stale(now=time.time()), [job_id])
        self.assertFalse(directory.exists())

    def test_recent_and_active_directories_are_preserved(self) -> None:
        storage = TemporaryJobStorage(self.root, max_age_seconds=60)
        recent_id = uuid.uuid4().hex
        active_id = uuid.uuid4().hex
        recent = storage.create_job_dir(recent_id)
        active = storage.create_job_dir(active_id)
        old_time = time.time() - 120
        os.utime(active, (old_time, old_time))
        storage.mark_active(active_id)

        self.assertEqual(storage.cleanup_stale(now=time.time()), [])
        self.assertTrue(recent.exists())
        self.assertTrue(active.exists())

    def test_path_traversal_cannot_remove_outside_root(self) -> None:
        storage = TemporaryJobStorage(self.root, max_age_seconds=60)
        outside = Path(self.temporary_directory.name) / "outside.txt"
        outside.write_text("keep", encoding="utf-8")

        with self.assertRaises(ValueError):
            storage.remove_job("../outside.txt")

        self.assertEqual(outside.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
