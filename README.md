# VidKit Backend

FastAPI backend for [VidKit](../PROJECT.md) video, image, PDF, audio, and developer utility tools.
Deployment (Render + Neon/Supabase): see [DEPLOYMENT.md](../DEPLOYMENT.md).

> **Legal notice:** Only download or process content you own or have permission to use.
> Respect platform Terms of Service and copyright law.

## Requirements

- Python 3.11+ (the Docker image uses 3.12)
- FFmpeg and ffprobe on `PATH` (video + audio tools)
- Optional system tools (each feature returns `DEPENDENCY_MISSING` if its tool is absent):
  - **Ghostscript**: PDF compress
  - **LibreOffice** (`soffice`): PDF ↔ Word
  - **Poppler**: PDF → JPG / OCR rendering (`pdf2image`)
  - **Tesseract OCR**: searchable PDF OCR
  - **Pandoc**: Markdown convert (PDF output also needs a PDF engine such as pdflatex)
  - **Deno**: JavaScript runtime yt-dlp uses for YouTube
  - **demucs** (Python, pulls PyTorch): vocal remover; first run downloads model weights

The [Dockerfile](Dockerfile) installs all of these. Locally you only need the ones for the tools you are working on.

### Windows installs

```powershell
winget install Gyan.FFmpeg
winget install ArtifexSoftware.GhostScript
winget install TheDocumentFoundation.LibreOffice
winget install UB-Mannheim.TesseractOCR
winget install JohnMacFarlane.Pandoc
winget install DenoLand.Deno
# Poppler: download a Windows build and set POPPLER_PATH to its bin folder
```

Restart the terminal afterwards. If a tool is not on `PATH`, set its `*_PATH` variable in `.env`.
On Windows Ghostscript is often `gswin64c`; the backend looks for that automatically.

## Setup

```powershell
cd vidkit-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt   # runtime deps + pytest
Copy-Item .env.example .env
alembic upgrade head
```

`demucs` pulls **PyTorch** and is large. To skip it, install the other lines of `requirements.txt` only;
the vocal remover then returns `DEPENDENCY_MISSING`.

## Run

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Health check: `curl http://localhost:8000/api/health` (also reports ffmpeg / yt-dlp versions)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Run **one** worker process. The job queue, progress, and cancel state live in-process
([app/workers/runner.py](app/workers/runner.py)), so multiple workers or instances would not see each other's jobs.

## Database

| Environment | `DATABASE_URL` |
|---|---|
| Local | `sqlite:///./vidkit.db` (default) |
| Neon / Supabase / Render Postgres | Paste the provider's `postgresql://...` URL as-is |

Plain `postgres://` / `postgresql://` URLs are rewritten to the psycopg 3 driver (`postgresql+psycopg://`).
Migrations run with `alembic upgrade head`; the Docker image runs this on every start.

Tables: `jobs`, `job_files`, `short_urls`, `users` (scaffolded for future accounts, unused today).

## Docker

```bash
docker build -t vidkit-api .                                   # default: no vocal remover, fits 512 MB hosts
docker build --build-arg INSTALL_DEMUCS=true -t vidkit-api .   # adds Demucs/PyTorch (~1.5 GB, needs 2-4 GB RAM)
docker run -p 8000:8000 --env-file .env vidkit-api
```

The container listens on `$PORT` (default 8000) and trusts `X-Forwarded-For` from the host's proxy, so rate limits apply per real client IP.

## Tests

```powershell
pytest -q
```

Splitter and audio tests skip when ffmpeg is missing; PDF compress tests skip when Ghostscript is missing.

## Updating yt-dlp

Extractors break periodically. Locally: `pip install -U "yt-dlp[default]"`. In production, redeploy
(Render: Manual Deploy → *Clear build cache & deploy*) to pick up the latest release.

For content that needs a login, set `YTDLP_COOKIES_FILE` to a Netscape-format cookies file.

## API overview

- Video: `/api/video/*`, `/api/split`, `/api/compress`, `/api/extract`, `/api/trim`, `/api/convert`, `/api/merge`, `/api/gif`, `/api/rotate`, `/api/resize`
- Image: `/api/image/*`
- PDF: `/api/pdf/*`
- Audio: `/api/audio/*`
- Tools: `POST /api/tools/markdown`, `POST /api/tools/shorten`, `GET /r/{code}`
- Jobs and files: `/api/jobs/{id}`, `/api/jobs/{id}/events` (SSE), `/api/jobs/{id}/zip`, `/api/files/{id}/download`
