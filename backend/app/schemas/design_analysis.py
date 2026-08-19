from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.agents.types import DesignAnalysisResult
from app.integrations.imaging.types import ComparisonResult
from app.integrations.llm.types import VisualReviewResult


class DesignAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    model: str
    result: DesignAnalysisResult
    production_screenshot_key: str | None
    comparison_result: ComparisonResult | None
    diff_image_key: str | None
    visual_comparison: VisualReviewResult | None
    created_at: datetime
