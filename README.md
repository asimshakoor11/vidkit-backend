# VidKit Backend

FastAPI backend for [VidKit](../PROJECT.md) video tools (downloader + splitter).

> **Legal notice:** Only download or process content you own or have permission to use.
> Respect platform Terms of Service and copyright law.

## Requirements

- Python 3.11+
- FFmpeg and ffprobe on `PATH`
- Node 18+ for the frontend (`vidkit-frontend`)

### Install FFmpeg (Windows)

```powershell
winget install Gyan.FFmpeg
# Restart the terminal, then:
ffmpeg -version
ffprobe -version
```

Or download a static build from [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/) and add its `bin` folder to PATH.
You can also set `FFMPEG_PATH` / `FFPROBE_PATH` in `.env`.

## Setup

```powershell
cd vidkit-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
```



## Run

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```powershell
curl http://localhost:8000/api/health
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Tests

```powershell
pytest -q
```

Splitter tests generate a short sample video with ffmpeg and are skipped if ffmpeg is missing.

## Updating yt-dlp

Extractors break periodically:

```powershell
pip install -U yt-dlp
```

For Instagram/Facebook content that needs login, set `YTDLP_COOKIES_FILE` in `.env` to a Netscape cookies file.

## Frontend

In `vidkit-frontend/.env.local`:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Then `npm run dev` (Next.js defaults to [http://localhost:3000](http://localhost:3000)).