from __future__ import annotations

import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path


JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
logger = logging.getLogger(__name__)


class TemporaryJobStorage:
    def __init__(self, root: Path, max_age_seconds: int) -> None:
        self.root = root.expanduser().resolve()
        self.max_age_seconds = max(1, max_age_seconds)
        self.root.mkdir(parents=True, exist_ok=True)
        self._active_job_ids: set[str] = set()
        self._active_lock = threading.Lock()

    def create_job_dir(self, job_id: str) -> Path:
        path = self._job_path(job_id)
        path.mkdir(parents=False, exist_ok=False)
        return path

    def mark_active(self, job_id: str) -> None:
        self._validate_job_id(job_id)
        with self._active_lock:
            self._active_job_ids.add(job_id)

    def mark_inactive(self, job_id: str) -> None:
        with self._active_lock:
            self._active_job_ids.discard(job_id)

    def active_job_ids(self) -> set[str]:
        with self._active_lock:
            return set(self._active_job_ids)

    def remove_job(self, job_id: str) -> bool:
        path = self._job_path(job_id)
        if not path.exists() and not path.is_symlink():
            return False
        if path.is_symlink():
            logger.warning("temporary cleanup skipped job_id=%s result=unsafe_symlink", job_id)
            return False

        resolved = path.resolve()
        if resolved.parent != self.root:
            logger.warning("temporary cleanup skipped job_id=%s result=outside_root", job_id)
            return False

        shutil.rmtree(resolved)
        logger.info("temporary cleanup job_id=%s result=removed", job_id)
        return True

    def cleanup_stale(self, now: float | None = None) -> list[str]:
        current_time = time.time() if now is None else now
        active = self.active_job_ids()
        removed: list[str] = []

        with os.scandir(self.root) as entries:
            for entry in entries:
                if entry.name in active or not JOB_ID_PATTERN.fullmatch(entry.name):
                    continue
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    continue
                try:
                    modified_at = entry.stat(follow_symlinks=False).st_mtime
                except FileNotFoundError:
                    continue
                if current_time - modified_at <= self.max_age_seconds:
                    continue
                if self.remove_job(entry.name):
                    removed.append(entry.name)

        return removed

    def _job_path(self, job_id: str) -> Path:
        self._validate_job_id(job_id)
        path = self.root / job_id
        if path.parent.resolve() != self.root:
            raise ValueError("Unsafe temporary job path.")
        return path

    @staticmethod
    def _validate_job_id(job_id: str) -> None:
        if not JOB_ID_PATTERN.fullmatch(job_id):
            raise ValueError("Invalid download job ID.")
