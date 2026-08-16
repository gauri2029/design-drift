from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.integrations.imaging.types import ComparisonResult


class ScanCreate(BaseModel):
    viewport_width: int = 1280
    viewport_height: int = 800


class ScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    viewport_width: int
    viewport_height: int
    production_screenshot_key: str
    diff_image_key: str
    # Raw pixel-diff result (see ComparisonResult's docstring) — not a
    # design fidelity score.
    comparison_result: ComparisonResult
    created_at: datetime
