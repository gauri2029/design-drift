from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.agents.types import DesignAnalysisResult


class DesignAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    model: str
    result: DesignAnalysisResult
    production_screenshot_key: str | None
    created_at: datetime
