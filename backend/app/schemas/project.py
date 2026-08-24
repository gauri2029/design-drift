from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

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


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    figma_file_key: str
    figma_node_id: str
    target_url: str
    target_selector: str | None = None
    source_path: str | None = None

    figma_data: FigmaNode | None = None
    figma_screenshot_key: str | None = None
    figma_fetched_at: datetime | None = None

    created_at: datetime
    updated_at: datetime
