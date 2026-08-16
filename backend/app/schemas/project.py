from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.integrations.figma.types import FigmaNode


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    figma_file_key: str = Field(min_length=1)
    figma_node_id: str = Field(min_length=1)
    target_url: HttpUrl


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    figma_file_key: str
    figma_node_id: str
    target_url: str

    figma_data: FigmaNode | None = None
    figma_screenshot_key: str | None = None
    figma_fetched_at: datetime | None = None

    created_at: datetime
    updated_at: datetime
