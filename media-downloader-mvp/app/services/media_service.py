from __future__ import annotations

import asyncio
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import yt_dlp
from fastapi import HTTPException, status
from yt_dlp.networking.impersonate import ImpersonateTarget

from app.core.config import Settings
from app.models.schemas import MediaFormat
from app.services.privacy import (
    is_snapchat_authentication_error,
    reject_private_metadata,
    reject_story_metadata,
    translate_extractor_error,
)
from app.services.url_guard import is_snapchat_spotlight_url
from app.services.temp_storage import TemporaryJobStorage


SAFE_FORMAT_ID = re.compile(r"^[A-Za-z0-9_.:+,-]{1,200}$")
SNAPCHAT_WATERMARKED_MESSAGE = (
    "Snapchat only provided a branded Spotlight sharing preview; "
    "a clean original video stream is unavailable for this post."
)
ProgressCallback = Callable[[dict[str, Any]], None]
logger = logging.getLogger(__name__)


def _is_snapchat_watermarked_variant(media_url: str) -> bool:
    parsed = urlparse(media_url)
    return bool(re.search(r"\.27\.[^/]+$", parsed.path, re.IGNORECASE))


def _select_clean_snapchat_format(info: dict[str, Any]) -> str:
    candidates = list(info.get("formats") or [])
    if not candidates and info.get("url"):
        candidates = [info]

    clean_candidates: list[dict[str, Any]] = []
    for item in candidates:
        media_url = str(item.get("url") or "")
        parsed = urlparse(media_url)
        watermarked = _is_snapchat_watermarked_variant(media_url)
        logger.info(
            "Snapchat format candidate id=%s resolution=%sx%s ext=%s host=%s path=%s rejected_watermarked=%s",
            item.get("format_id"),
            item.get("width"),
            item.get("height"),
            item.get("ext"),
            parsed.hostname,
            parsed.path,
            watermarked,
        )
        if (
            media_url
            and parsed.scheme == "https"
            and parsed.hostname
            and (
                parsed.hostname == "sc-cdn.net"
                or parsed.hostname.endswith(".sc-cdn.net")
            )
            and item.get("vcodec") != "none"
            and not watermarked
        ):
            clean_candidates.append(item)

    if not clean_candidates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=SNAPCHAT_WATERMARKED_MESSAGE,
        )

    selected = max(
        clean_candidates,
        key=lambda item: (
            int(item.get("height") or 0) * int(item.get("width") or 0),
            float(item.get("tbr") or 0),
            int(item.get("filesize") or item.get("filesize_approx") or 0),
        ),
    )
    return str(selected.get("format_id") or "0")


class DownloadCanceledError(Exception):
    pass


class MediaService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
        self.storage = TemporaryJobStorage(
            settings.temp_root,
            settings.temp_file_max_age_seconds,
        )

    def _base_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "impersonate": ImpersonateTarget.from_str("chrome"),
            # Intentionally no cookies, username, password, or browser session.
        }
        if self.settings.ffmpeg_location:
            options["ffmpeg_location"] = self.settings.ffmpeg_location
        return options

    async def inspect(self, url: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._inspect_sync, url)

    def _inspect_sync(self, url: str) -> dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL(self._base_options()) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            raise translate_extractor_error(exc, url) from exc

        if not isinstance(info, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No downloadable media was found.",
            )

        reject_story_metadata(info, url)
        reject_private_metadata(info)
        self._enforce_limits(info)

        formats: list[MediaFormat] = []
        for item in info.get("formats") or []:
            format_id = str(item.get("format_id") or "")
            if not format_id:
                continue

            video_codec = item.get("vcodec")
            audio_codec = item.get("acodec")
            has_video = video_codec not in (None, "none")
            has_audio = audio_codec not in (None, "none")

            formats.append(
                MediaFormat(
                    format_id=format_id,
                    extension=item.get("ext"),
                    width=item.get("width"),
                    height=item.get("height"),
                    resolution=item.get("resolution"),
                    video_codec=video_codec,
                    audio_codec=audio_codec,
                    filesize=item.get("filesize") or item.get("filesize_approx"),
                    bitrate=item.get("tbr"),
                    has_video=has_video,
                    has_audio=has_audio,
                )
            )

        media_kind = "image" if not formats and info.get("thumbnail") else "video"
        duration = info.get("duration")

        return {
            "platform": info.get("extractor_key") or info.get("extractor"),
            "media_id": info.get("id"),
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "duration": round(duration) if isinstance(duration, (int, float)) else None,
            "thumbnail": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url") or url,
            "media_kind": media_kind,
            "formats": formats,
        }

    async def download(
        self,
        url: str,
        mode: str,
        format_id: str | None,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        on_start: Callable[[], None] | None = None,
        job_id: str | None = None,
    ) -> Path:
        async with self._semaphore:
            if on_start:
                on_start()
            return await asyncio.to_thread(
                self._download_sync,
                url,
                mode,
                format_id,
                progress_callback,
                cancel_event,
                job_id,
            )

    def _download_sync(
        self,
        url: str,
        mode: str,
        format_id: str | None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        job_id: str | None = None,
    ) -> Path:
        job_id = job_id or uuid.uuid4().hex
        job_dir = self.storage.create_job_dir(job_id)
        self.storage.mark_active(job_id)
        retain_completed_file = False
        snapchat_spotlight = is_snapchat_spotlight_url(url)

        def report(update: dict[str, Any]) -> None:
            if progress_callback:
                progress_callback(update)

        def progress_hook(data: dict[str, Any]) -> None:
            if cancel_event and cancel_event.is_set():
                raise DownloadCanceledError()

            hook_status = data.get("status")
            if hook_status == "finished":
                report({"status": "finishing", "percentage": 100, "eta": 0})
                return
            if hook_status != "downloading":
                return

            downloaded = int(data.get("downloaded_bytes") or 0)
            total_value = data.get("total_bytes") or data.get("total_bytes_estimate")
            total = int(total_value) if total_value else None
            percentage = min(100.0, downloaded * 100 / total) if total else 0.0
            report(
                {
                    "status": "downloading",
                    "percentage": percentage,
                    "downloaded_bytes": downloaded,
                    "total_bytes": total,
                    "speed": float(data["speed"]) if data.get("speed") else None,
                    "eta": float(data["eta"]) if data.get("eta") is not None else None,
                }
            )

        def postprocessor_hook(data: dict[str, Any]) -> None:
            if cancel_event and cancel_event.is_set():
                raise DownloadCanceledError()
            if data.get("status") in {"started", "processing"}:
                report({"status": "finishing", "percentage": 100, "eta": 0})

        try:
            if cancel_event and cancel_event.is_set():
                raise DownloadCanceledError()
            snapchat_format_id: str | None = None
            if snapchat_spotlight and mode == "video":
                try:
                    with yt_dlp.YoutubeDL(self._base_options()) as ydl:
                        snapchat_info = ydl.extract_info(url, download=False)
                except Exception as exc:
                    raise translate_extractor_error(exc, url) from exc
                if not isinstance(snapchat_info, dict):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=SNAPCHAT_WATERMARKED_MESSAGE,
                    )
                snapchat_format_id = _select_clean_snapchat_format(snapchat_info)

            options: dict[str, Any] = {
                **self._base_options(),
                "skip_download": False,
                "outtmpl": str(
                    job_dir / ("spotlight.%(ext)s" if snapchat_spotlight else "%(id)s.%(ext)s")
                ),
                "paths": {"home": str(job_dir), "temp": str(job_dir)},
                "cachedir": False,
                "restrictfilenames": True,
                "overwrites": False,
                "max_filesize": self.settings.max_file_size_mb * 1024 * 1024,
                "progress_hooks": [progress_hook],
                "postprocessor_hooks": [postprocessor_hook],
            }

            if snapchat_format_id is not None:
                if format_id is not None and format_id != snapchat_format_id:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=SNAPCHAT_WATERMARKED_MESSAGE,
                    )
                options["format"] = snapchat_format_id
            elif format_id:
                if not SAFE_FORMAT_ID.fullmatch(format_id):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid format ID.",
                    )
                options["format"] = format_id
            elif mode == "video":
                options["format"] = "bv*+ba/b"
                options["merge_output_format"] = "mp4"
            elif mode == "audio":
                options["format"] = "bestaudio/best"
                options["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ]
            elif mode == "image":
                options["skip_download"] = True
                options["writethumbnail"] = True
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unsupported download mode.",
                )

            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=True)
            except HTTPException:
                raise
            except Exception as exc:
                if cancel_event and cancel_event.is_set():
                    raise DownloadCanceledError() from exc
                should_retry = (
                    snapchat_spotlight
                    and mode == "video"
                    and format_id is not None
                    and not is_snapchat_authentication_error(exc)
                )
                if not should_retry:
                    raise translate_extractor_error(exc, url) from exc

                self.storage.remove_job(job_id)
                job_dir = self.storage.create_job_dir(job_id)
                retry_options = {
                    **options,
                    "format": "bv*+ba/b",
                    "merge_output_format": "mp4",
                }
                try:
                    with yt_dlp.YoutubeDL(retry_options) as ydl:
                        info = ydl.extract_info(url, download=True)
                except Exception as retry_exc:
                    if cancel_event and cancel_event.is_set():
                        raise DownloadCanceledError() from retry_exc
                    raise translate_extractor_error(retry_exc, url) from retry_exc

            if not isinstance(info, dict):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="No downloadable media was found.",
                )

            reject_story_metadata(info, url)
            reject_private_metadata(info)
            self._enforce_limits(info)

            if cancel_event and cancel_event.is_set():
                raise DownloadCanceledError()
            report({"status": "finishing", "percentage": 100, "eta": 0})

            files = [
                path
                for path in job_dir.iterdir()
                if path.is_file() and not path.name.endswith((".part", ".ytdl"))
            ]
            if not files:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="The media file could not be created.",
                )

            result = max(files, key=lambda path: path.stat().st_mtime)
            retain_completed_file = True
            return result

        finally:
            self.storage.mark_inactive(job_id)
            if not retain_completed_file:
                self.storage.remove_job(job_id)

    def cleanup_job(self, job_id: str) -> None:
        self.storage.remove_job(job_id)

    def _enforce_limits(self, info: dict[str, Any]) -> None:
        duration = info.get("duration")
        if isinstance(duration, (int, float)) and duration > self.settings.max_duration_seconds:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="The media is longer than the configured limit.",
            )
