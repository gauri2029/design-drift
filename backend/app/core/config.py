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

    database_url: str = "postgresql+asyncpg://design_drift:design_drift@localhost:5432/design_drift"

    # Root directory for locally-stored artifacts (screenshots, renders).
    # Relative to backend/'s working directory, so it lands at repo-root/storage.
    storage_root: str = "../storage"

    # Root directory under which target apps' source checkouts live. A
    # Project's `source_path` is resolved *relative to this* and confined
    # inside it (see app.tools.repo_search.resolve_source_root) rather than
    # being an arbitrary absolute path: the Code Analysis Agent reads these
    # files and sends what it finds to a third-party LLM API, so an
    # unconstrained path would turn a project field into "read any file
    # this process can reach, then upload it".
    source_root: str = "../sources"

    figma_access_token: str = ""
    figma_api_base_url: str = "https://api.figma.com/v1"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"

    # Which provider backs app.integrations.llm.client.generate_structured():
    # "anthropic" or "gemini". Gemini's free tier is the low/no-cost dev
    # option (see app.integrations.llm.gemini_client's docstring).
    llm_provider: str = "anthropic"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def llm_model(self) -> str:
        """Whichever model name generate_structured() actually calls right
        now — for callers (app.services.reviews, app.services.design_analysis)
        that record it as an audit/reproducibility trail alongside a result.
        """
        return self.gemini_model if self.llm_provider == "gemini" else self.anthropic_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
