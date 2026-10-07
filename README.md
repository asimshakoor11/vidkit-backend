# VidKit Backend

FastAPI backend for [VidKit](../PROJECT.md) video, image, PDF, audio, and developer utility tools.

> **Legal notice:** Only download or process content you own or have permission to use.
> Respect platform Terms of Service and copyright law.

## Requirements

- Python 3.11+
- FFmpeg and ffprobe on `PATH` (video + audio tools)
- Node 18+ for the frontend (`vidkit-frontend`)
- Optional for PDF tools (features skip/fail with a clear error if missing):
  - **Ghostscript** — PDF compress
  - **LibreOffice** (`soffice`) — PDF ↔ Word
  - **Poppler** — PDF → JPG / OCR rendering (`pdf2image`)
  - **Tesseract OCR** — searchable PDF OCR
- Optional for vocal remover: **demucs** (`pip install demucs`) — first run downloads model weights; CPU works, GPU recommended
- Optional for Markdown convert: **Pandoc** on `PATH` (PDF also needs a PDF engine such as pdflatex)

### Install FFmpeg (Windows)

```powershell
winget install Gyan.FFmpeg
# Restart the terminal, then:
ffmpeg -version
ffprobe -version
```

Or download a static build from [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/) and add its `bin` folder to PATH.
You can also set `FFMPEG_PATH` / `FFPROBE_PATH` in `.env`.

### Install PDF binaries (Windows)

```powershell
winget install ArtifexSoftware.GhostScript
winget install TheDocumentFoundation.LibreOffice
winget install UB-Mannheim.TesseractOCR
# Poppler: download a Windows build and set POPPLER_PATH to its bin folder
```

Set paths in `.env` if they are not on `PATH`:

```
GS_PATH=gs
LIBREOFFICE_PATH=soffice
TESSERACT_PATH=tesseract
POPPLER_PATH=C:\path\to\poppler\Library\bin
AUDIO_SEPARATE_TIMEOUT_SEC=900
PANDOC_PATH=pandoc
MARKDOWN_TIMEOUT_SEC=120
PUBLIC_BASE_URL=http://localhost:8000
SHORT_URL_TTL_DAYS=30
```

On Windows Ghostscript is often `gswin64c` — the backend also looks for that automatically.

### Install Pandoc (Windows)

```powershell
winget install JohnMacFarlane.Pandoc
pandoc -v
```

PDF output needs a Pandoc PDF engine (e.g. a LaTeX distribution). HTML conversion works with Pandoc alone.

## Setup

```powershell
cd vidkit-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
```

Note: `demucs` pulls **PyTorch** and is large. If you only need FFmpeg audio tools, you can skip installing demucs and vocal separation will return `DEPENDENCY_MISSING`.

## Run

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```powershell
curl http://localhost:8000/api/health
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

- PDF endpoints: `/api/pdf/*`
- Audio endpoints: `/api/audio/*` (convert, compress, trim, merge, denoise, separate)
- Tools endpoints: `POST /api/tools/markdown`, `POST /api/tools/shorten`, `GET /r/{code}`

## Tests

```powershell
pytest -q
```

Splitter tests generate a short sample video with ffmpeg and are skipped if ffmpeg is missing.
PDF compress tests skip when Ghostscript is missing.
Audio FFmpeg tests skip when ffmpeg is missing.

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
