import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DesignAnalysis(Base):
    """One Design Analysis Agent run against a project's Figma data.

    Project-scoped, not scan-scoped — this agent interprets the Figma side
    only (see app.agents.design_analysis), independent of any particular
    production scan. A project can be re-analyzed (e.g. after a model
    change or a Figma re-fetch), hence a separate table rather than a
    single field on Project — same one-to-many shape as Project -> Scan.

    `result` mirrors app.agents.types.DesignAnalysisResult, stored as
    JSONB for the same reason as Review.result: a small fixed-shape record
    with no query/filter need yet.
    """

    __tablename__ = "design_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # Which model produced this analysis — an audit/reproducibility trail,
    # same rationale as Review.model.
    model: Mapped[str] = mapped_column(nullable=False)
    result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
