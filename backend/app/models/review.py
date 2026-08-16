import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Review(Base):
    """One multimodal LLM review of a scan.

    A scan can be reviewed more than once (e.g. re-run after a model
    change), hence a separate table rather than fields on Scan — same
    one-to-many shape as Project -> Scan.

    `result` mirrors app.integrations.llm.types.VisualReviewResult exactly,
    stored as JSONB for the same reason as Scan.comparison_result: a small
    fixed-shape record with no query/filter need yet.
    """

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )

    # Which model produced this review — an audit/reproducibility trail,
    # since app.core.config.Settings.anthropic_model can change over time.
    model: Mapped[str] = mapped_column(nullable=False)
    result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
