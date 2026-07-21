# Public Media Downloader MVP

FastAPI + yt-dlp MVP for publicly accessible media only.

## Privacy rule

- Public post/video/image: allowed when it is reachable without login. Story downloads are rejected.
- Private, followers-only, friends-only, login-required, or cookie-required content: rejected.
- The backend intentionally does not accept or load browser cookies, usernames, passwords, or sessions.
- Use only for content you own or have permission to download.

## Project structure

```text
media-downloader-mvp/
├── app/
│   ├── core/config.py
│   ├── models/schemas.py
│   ├── services/
│   │   ├── media_service.py
│   │   ├── privacy.py
│   │   └── url_guard.py
│   └── main.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── downloads/
├── .env.example
├── requirements.txt
└── README.md
```

## Windows setup

1. Install FFmpeg and make sure this works:

```cmd
ffmpeg -version
```

2. Open CMD inside the project folder:

```cmd
py -m venv .venv
.venv\Scripts\activate
py -m pip install -U pip
pip install -r requirements.txt
copy .env.example .env
```

3. Run the application (backend and frontend):

```cmd
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open the application and backend docs:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/docs
```

The frontend uses the current origin by default. For a separately hosted frontend,
set `window.ONE_MEDIA_API_BASE_URL` before loading `app.js` and allow that origin
with `FRONTEND_ORIGINS`.

## Docker

Copy `.env.example` to `.env`, set `ALLOWED_HOSTS` to the deployment hostname or
public IP, and set `FRONTEND_ORIGINS` to the public site origin. Then run:

```sh
docker compose up --build -d
```

The container runs as a non-root user, includes FFmpeg, binds to `0.0.0.0:8000`,
and stores job files on a size-limited temporary filesystem.

## API

### Inspect

```http
POST /api/inspect
Content-Type: application/json

{"url":"https://example.com/public-media-url"}
```

### Download

```http
POST /api/download
Content-Type: application/json

{
  "url":"https://example.com/public-media-url",
  "mode":"video",
  "format_id":null
}
```

Modes: `video`, `audio`, `image`.

### Queued download with live progress

```http
POST /api/downloads
GET /api/downloads/{job_id}
GET /api/downloads/{job_id}/events
GET /api/downloads/{job_id}/file
DELETE /api/downloads/{job_id}
POST /api/downloads/{job_id}/retry
GET /health
```

The events route uses Server-Sent Events and reports status, percentage, byte counts, speed, and ETA. Completed files and in-memory job records expire automatically according to `DOWNLOAD_TTL_SECONDS`. The original `POST /api/download` route remains available for backward compatibility.

Every download uses an isolated directory under `TEMP_ROOT` (default `./temp/jobs`). Failed, canceled, and timed-out jobs are removed after the downloader exits. Completed files remain until response delivery finishes, then a background callback removes the job directory. Startup and periodic cleanup remove stale directories older than `TEMP_FILE_MAX_AGE_SECONDS`; `CLEANUP_INTERVAL_SECONDS` controls the scan interval.

## Important limitations

- Stories are intentionally unsupported, including public stories.
- A platform update can temporarily break an extractor.
- Some formats need FFmpeg to merge video and audio.
- Download queue state is stored in memory and is local to one backend process. Multi-worker deployments should use a shared job store and object storage.
- Public deployments should add rate limiting, abuse controls, centralized logging, and platform-specific monitoring.
