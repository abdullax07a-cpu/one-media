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
ProgressCallback = Callable[[dict[str, Any]], None]
logger = logging.getLogger(__name__)

SNAPCHAT_VIDEO_EXTENSIONS = {"m4v", "mov", "mp4", "webm"}
SNAPCHAT_IMAGE_EXTENSIONS = {"avif", "gif", "heic", "jpeg", "jpg", "png", "webp"}
SNAPCHAT_AUDIO_EXTENSIONS = {"aac", "flac", "m4a", "mp3", "ogg", "opus", "wav"}


def _snapchat_media_candidates(info: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [dict(item) for item in info.get("formats") or [] if isinstance(item, dict)]
    direct_url = str(info.get("url") or "")
    if direct_url and not any(str(item.get("url") or "") == direct_url for item in candidates):
        direct = dict(info)
        direct["format_id"] = str(direct.get("format_id") or "0")
        candidates.append(direct)
    return candidates


def _is_valid_snapchat_video(item: dict[str, Any]) -> bool:
    media_url = str(item.get("url") or "")
    parsed = urlparse(media_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    extension = str(item.get("ext") or "").lower()
    video_codec = str(item.get("vcodec") or "").lower()
    descriptor = " ".join(
        str(item.get(key) or "")
        for key in ("format", "format_note", "format_id", "mime_type")
    ).lower()
    path = parsed.path.lower()

    if video_codec == "none" or extension in SNAPCHAT_AUDIO_EXTENSIONS:
        return False
    if (
        extension in SNAPCHAT_IMAGE_EXTENSIONS
        or any(marker in descriptor for marker in ("thumbnail", "poster", "storyboard"))
        or re.search(r"\.256\.[^/]+$", path)
    ):
        return False
    if video_codec:
        return True
    return bool(
        extension in SNAPCHAT_VIDEO_EXTENSIONS
        or str(item.get("video_ext") or "").lower() in SNAPCHAT_VIDEO_EXTENSIONS
        or (item.get("width") and item.get("height"))
    )


def _has_explicit_watermark_evidence(item: dict[str, Any]) -> bool:
    descriptor = " ".join(
        str(item.get(key) or "")
        for key in ("format", "format_note", "format_id", "source", "url")
    ).lower()
    return "watermark" in descriptor or "watermarked" in descriptor


def _snapchat_video_rank(item: dict[str, Any]) -> tuple[int, int, int, float, int, int]:
    parsed = urlparse(str(item.get("url") or ""))
    host = parsed.hostname or ""
    descriptor = " ".join(
        str(item.get(key) or "")
        for key in ("format", "format_note", "format_id", "source", "url")
    ).lower()
    is_snapchat_cdn = host == "sc-cdn.net" or host.endswith(".sc-cdn.net")
    looks_like_preview = any(marker in descriptor for marker in ("preview", "sharing", "share", "export"))
    priority = 3 if is_snapchat_cdn and not looks_like_preview else 2 if not looks_like_preview else 1
    pixels = int(item.get("width") or 0) * int(item.get("height") or 0)
    return (
        priority,
        pixels,
        int(item.get("height") or 0),
        float(item.get("tbr") or 0),
        int(item.get("filesize") or item.get("filesize_approx") or 0),
        int(str(item.get("acodec") or "").lower() not in {"", "none"}),
    )


def _select_snapchat_video_candidate(info: dict[str, Any]) -> dict[str, Any]:
    candidates = _snapchat_media_candidates(info)

    for item in candidates:
        media_url = str(item.get("url") or "")
        parsed = urlparse(media_url)
        valid_video = _is_valid_snapchat_video(item)
        explicit_watermark = _has_explicit_watermark_evidence(item)
        logger.info(
            "Snapchat format candidate id=%s resolution=%sx%s ext=%s vcodec=%s acodec=%s host=%s path=%s valid_video=%s explicit_watermark=%s",
            item.get("format_id"),
            item.get("width"),
            item.get("height"),
            item.get("ext"),
            item.get("vcodec"),
            item.get("acodec"),
            parsed.hostname,
            parsed.path,
            valid_video,
            explicit_watermark,
        )
    valid_candidates = [
        item
        for item in candidates
        if _is_valid_snapchat_video(item) and not _has_explicit_watermark_evidence(item)
    ]
    if not valid_candidates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No downloadable Snapchat video format was found.",
        )
    return max(valid_candidates, key=_snapchat_video_rank)


def _select_snapchat_format(info: dict[str, Any]) -> str:
    return str(_select_snapchat_video_candidate(info).get("format_id") or "0")


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
        snapchat_spotlight = is_snapchat_spotlight_url(url)
        extracted_formats = (
            [item for item in _snapchat_media_candidates(info) if _is_valid_snapchat_video(item)]
            if snapchat_spotlight
            else info.get("formats") or []
        )
        for item in extracted_formats:
            format_id = str(item.get("format_id") or "")
            if not format_id:
                continue

            video_codec = item.get("vcodec")
            audio_codec = item.get("acodec")
            has_video = _is_valid_snapchat_video(item) if snapchat_spotlight else video_codec not in (None, "none")
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
                        detail="No downloadable Snapchat video format was found.",
                    )
                selected_candidate = _select_snapchat_video_candidate(snapchat_info)
                valid_format_ids = {
                    str(item.get("format_id") or "0")
                    for item in _snapchat_media_candidates(snapchat_info)
                    if _is_valid_snapchat_video(item) and not _has_explicit_watermark_evidence(item)
                }
                snapchat_format_id = (
                    format_id
                    if format_id is not None and format_id in valid_format_ids
                    else str(selected_candidate.get("format_id") or "0")
                )
                chosen_candidate = next(
                    (
                        item
                        for item in _snapchat_media_candidates(snapchat_info)
                        if str(item.get("format_id") or "0") == snapchat_format_id
                    ),
                    selected_candidate,
                )
                snapchat_has_audio = str(chosen_candidate.get("acodec") or "").lower() not in {"", "none"}

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
                options["format"] = (
                    snapchat_format_id
                    if snapchat_has_audio
                    else f"{snapchat_format_id}+ba/{snapchat_format_id}"
                )
                options["merge_output_format"] = "mp4"
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
