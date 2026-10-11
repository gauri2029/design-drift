from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Module-level so `jwt_secret_is_default` compares against one definition
# rather than reading the field default back out of the model.
_DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"


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

    # Where cloned GitHub repositories land, one directory per analysis run.
    # Separate from source_root because the trust model differs: sources/ is
    # something a developer put there by hand, this is whatever a third
    # party's repository contains. Gitignored, and confined the same way.
    workspace_root: str = "../workspaces"

    # --- GitHub App (read-only; see app.integrations.github) -----------------
    # Empty by default: without an App configured, the GitHub endpoints
    # report that it's unconfigured and the sources/ workflow is unaffected.
    github_app_id: str = ""
    # PEM file for the App's private key, used to sign the short-lived JWT
    # that mints installation tokens. A path rather than the key itself so
    # the key never passes through an env var that might get logged.
    github_app_private_key_path: str = ""
    # The App's URL slug, for building the "Install" link.
    github_app_slug: str = ""

    # Signs access tokens. The default is a development placeholder: it is
    # checked into the repo, so any deployment keeping it would be handing
    # out forgeable tokens. app.main refuses to start outside local without
    # a real one rather than warning into a log nobody reads.
    jwt_secret_key: str = _DEV_JWT_SECRET
    access_token_expire_minutes: int = 60 * 24 * 7

    figma_access_token: str = ""
    figma_api_base_url: str = "https://api.figma.com/v1"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"

    # Which provider backs app.integrations.llm.client.generate_structured():
    # "anthropic" or "gemini". Gemini's free tier is the low/no-cost dev
    # option (see app.integrations.llm.gemini_client's docstring).
    llm_provider: str = "anthropic"
    gemini_api_key: str = ""
    # Verified against models.list() on the free tier. gemini_client falls
    # back to a second free model when this one is oversubscribed.
    gemini_model: str = "gemini-3.5-flash-lite"

    @property
    def jwt_secret_is_default(self) -> bool:
        return self.jwt_secret_key == _DEV_JWT_SECRET

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
