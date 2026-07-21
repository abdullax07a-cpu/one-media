from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Public Media Downloader"
    app_env: str = "development"
    frontend_origins: str = "http://127.0.0.1:5500,http://localhost:5500"
    allowed_hosts: str = "localhost,127.0.0.1"
    max_duration_seconds: int = 1800
    max_file_size_mb: int = 500
    download_ttl_seconds: int = 300
    download_timeout_seconds: int = 1800
    max_concurrent_downloads: int = 2
    download_dir: Path = Path("downloads")
    temp_root: Path = Path("temp/jobs")
    temp_file_max_age_seconds: int = 3600
    cleanup_interval_seconds: int = 600
    ffmpeg_location: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.frontend_origins.split(",") if item.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.temp_root.mkdir(parents=True, exist_ok=True)
    return settings
