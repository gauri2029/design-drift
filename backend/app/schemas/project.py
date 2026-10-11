from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.integrations.figma.types import FigmaNode


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    figma_file_key: str = Field(min_length=1)
    figma_node_id: str = Field(min_length=1)
    target_url: HttpUrl
    # CSS selector on target_url matching the Figma node, e.g. "#hero-cta".
    # Unset means a scan screenshots the full page instead of one element.
    target_selector: str | None = None
    # Path to this app's source checkout, relative to Settings.source_root
    # (e.g. "acme-marketing-site"). Absolute paths and anything escaping
    # that root are rejected — see app.tools.repo_search.resolve_source_root.
    source_path: str | None = None
    # "owner/repo" from the connect flow. Mutually exclusive with
    # source_path — a project reads from GitHub or from a local checkout,
    # and accepting both would leave which one wins implicit.
    github_repo_full_name: str | None = None
    github_branch: str | None = None

    @model_validator(mode="after")
    def _one_source_provider(self) -> "ProjectCreate":
        if self.github_repo_full_name and self.source_path:
            raise ValueError("give either a GitHub repository or a local source path, not both")
        if self.github_branch and not self.github_repo_full_name:
            raise ValueError("a branch only means something with a GitHub repository")
        return self


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    figma_file_key: str
    figma_node_id: str
    target_url: str
    target_selector: str | None = None
    source_path: str | None = None
    github_repo_full_name: str | None = None
    github_branch: str | None = None

    figma_data: FigmaNode | None = None
    figma_screenshot_key: str | None = None
    figma_fetched_at: datetime | None = None

    created_at: datetime
    updated_at: datetime
