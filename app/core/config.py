"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the VidKit API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Stored as a plain string so dotenv/env values are not JSON-decoded.
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    database_url: str = "sqlite:///./vidkit.db"
    storage_dir: Path = Path("./storage")
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    gs_path: str = "gs"
    libreoffice_path: str = "soffice"
    tesseract_path: str = "tesseract"
    poppler_path: str = ""
    ytdlp_cookies_file: str = ""
    max_upload_mb: int = 4096
    max_video_duration_min: int = 180
    max_concurrent_jobs: int = 2
    file_ttl_minutes: int = 60
    rate_limit_info: str = "10/minute"
    rate_limit_jobs: str = "5/hour"
    pdf_convert_timeout_sec: int = 300
    audio_separate_timeout_sec: int = 900

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed CORS origins list."""
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def max_upload_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_video_duration_seconds(self) -> int:
        """Maximum allowed video duration in seconds."""
        return self.max_video_duration_min * 60

    @property
    def uploads_dir(self) -> Path:
        """Directory for uploaded input files."""
        return self.storage_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        """Directory for job output files."""
        return self.storage_dir / "outputs"

    @property
    def tmp_dir(self) -> Path:
        """Directory for temporary files."""
        return self.storage_dir / "tmp"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
