from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    log_level: str = "INFO"

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    database_url: str = (
        "postgresql+asyncpg://design_drift:design_drift@localhost:5432/design_drift"
    )

    # Root directory for locally-stored artifacts (screenshots, renders).
    # Relative to backend/'s working directory, so it lands at repo-root/storage.
    storage_root: str = "../storage"

    figma_access_token: str = ""
    figma_api_base_url: str = "https://api.figma.com/v1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
