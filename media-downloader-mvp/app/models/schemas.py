from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class InspectRequest(BaseModel):
    url: HttpUrl


class DownloadRequest(BaseModel):
    url: HttpUrl
    mode: Literal["video", "audio", "image"] = "video"
    format_id: str | None = Field(default=None, max_length=200)


class DownloadJobCreated(BaseModel):
    job_id: str
    status: str = "queued"


class DownloadJobStatus(BaseModel):
    job_id: str
    status: Literal[
        "queued",
        "preparing",
        "downloading",
        "finishing",
        "completed",
        "failed",
        "canceled",
    ]
    percentage: float = 0
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    speed: float | None = None
    eta: float | None = None
    filename: str | None = None
    error: str | None = None


class MediaFormat(BaseModel):
    format_id: str
    extension: str | None = None
    width: int | None = None
    height: int | None = None
    resolution: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    filesize: int | None = None
    bitrate: float | None = None
    has_video: bool
    has_audio: bool


class InspectResponse(BaseModel):
    success: bool = True
    platform: str | None = None
    media_id: str | None = None
    title: str | None = None
    uploader: str | None = None
    duration: int | None = None
    thumbnail: str | None = None
    webpage_url: str | None = None
    media_kind: str
    formats: list[MediaFormat]
