from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, get_settings
from app.models.schemas import (
    DownloadJobCreated,
    DownloadJobStatus,
    DownloadRequest,
    InspectRequest,
    InspectResponse,
)
from app.services.download_manager import DownloadManager
from app.services.media_service import MediaService
from app.services.url_guard import validate_public_url


settings = get_settings()
service = MediaService(settings)
download_manager = DownloadManager(
    service,
    settings.download_ttl_seconds,
    settings.download_timeout_seconds,
)


async def cleanup_stale_jobs_periodically() -> None:
    while True:
        await asyncio.sleep(max(1, settings.cleanup_interval_seconds))
        await asyncio.to_thread(service.storage.cleanup_stale)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(service.storage.cleanup_stale)
    cleanup_task = asyncio.create_task(cleanup_stale_jobs_periodically())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Downloads publicly accessible media only. "
        "No cookies, logins, or private-account access are used."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition"],
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/inspect", response_model=InspectResponse)
async def inspect_media(payload: InspectRequest) -> InspectResponse:
    url = validate_public_url(str(payload.url))
    result = await service.inspect(url)
    return InspectResponse(**result)


@app.post("/api/download")
async def download_media(
    payload: DownloadRequest,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    url = validate_public_url(str(payload.url))
    file_path = await service.download(url, payload.mode, payload.format_id)

    background_tasks.add_task(service.cleanup_job, file_path.parent.name)

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
        background=background_tasks,
    )


@app.post("/api/downloads", response_model=DownloadJobCreated, status_code=202)
async def create_download_job(payload: DownloadRequest) -> DownloadJobCreated:
    url = validate_public_url(str(payload.url))
    job = download_manager.create(payload.model_copy(update={"url": url}))
    return DownloadJobCreated(job_id=job.job_id, status=job.status)


@app.get("/api/downloads/{job_id}", response_model=DownloadJobStatus)
async def get_download_job(job_id: str) -> DownloadJobStatus:
    return DownloadJobStatus(**download_manager.get(job_id).snapshot())


@app.get("/api/downloads/{job_id}/events")
async def stream_download_job(job_id: str) -> StreamingResponse:
    download_manager.get(job_id)
    return StreamingResponse(
        download_manager.events(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/downloads/{job_id}/file")
async def get_downloaded_file(
    job_id: str,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    file_path = download_manager.completed_file(job_id)
    background_tasks.add_task(download_manager.remove_file, job_id)
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
        background=background_tasks,
    )


@app.delete("/api/downloads/{job_id}", response_model=DownloadJobStatus)
async def cancel_download_job(job_id: str) -> DownloadJobStatus:
    job = await download_manager.cancel(job_id)
    return DownloadJobStatus(**job.snapshot())


@app.post("/api/downloads/{job_id}/retry", response_model=DownloadJobCreated, status_code=202)
async def retry_download_job(job_id: str) -> DownloadJobCreated:
    job = download_manager.retry(job_id)
    return DownloadJobCreated(job_id=job.job_id, status=job.status)


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
