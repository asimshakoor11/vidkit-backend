# VidKit API — FastAPI + FFmpeg + PDF/OCR/Office binaries.
# Build:  docker build -t vidkit-api .                                   (no vocal remover; fits 512 MB hosts)
#         docker build --build-arg INSTALL_DEMUCS=true -t vidkit-api .   (adds Demucs/PyTorch; needs ~2-4 GB RAM)
# Run:    docker run -p 8000:8000 --env-file .env vidkit-api

# Deno is the JavaScript runtime yt-dlp needs for YouTube.
FROM denoland/deno:bin-2.9.8 AS deno

FROM python:3.12-slim-bookworm

ARG INSTALL_DEMUCS=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STORAGE_DIR=/app/storage

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg \
      ghostscript \
      poppler-utils \
      tesseract-ocr \
      tesseract-ocr-eng \
      libreoffice-writer-nogui \
      pandoc \
      fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

COPY --from=deno /deno /usr/local/bin/deno

WORKDIR /app

# Install everything except demucs first so this layer caches well.
COPY requirements.txt .
RUN grep -v '^demucs' requirements.txt > /tmp/requirements-base.txt \
 && pip install -r /tmp/requirements-base.txt

# Demucs pulls PyTorch; use the CPU-only wheels (~2GB smaller than the CUDA build).
RUN if [ "$INSTALL_DEMUCS" = "true" ]; then \
      pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu \
      && pip install "$(grep '^demucs' requirements.txt)"; \
    fi

COPY . .
RUN mkdir -p "$STORAGE_DIR"

EXPOSE 8000

# Single worker on purpose: the job queue, progress and cancel state live in-process.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
