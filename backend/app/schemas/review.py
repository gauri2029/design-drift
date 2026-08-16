from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.integrations.llm.types import VisualReviewResult


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scan_id: UUID
    model: str
    result: VisualReviewResult
    created_at: datetime
