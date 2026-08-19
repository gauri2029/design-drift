import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DesignAnalysis(Base):
    """One Design QA workflow run against a project (see app.graph.state's
    DesignQAState and app.services.design_analysis).

    Project-scoped, not scan-scoped — the workflow analyzes a project's
    Figma side and captures its production app independent of any
    particular pixel-diff Scan. A project can be re-analyzed (e.g. after a
    model change, a Figma re-fetch, or a production deploy), hence a
    separate table rather than a single field on Project — same
    one-to-many shape as Project -> Scan.

    `result` mirrors app.agents.types.DesignAnalysisResult, stored as
    JSONB for the same reason as Review.result: a small fixed-shape record
    with no query/filter need yet. `production_screenshot_key`,
    `comparison_result`, `diff_image_key`, `visual_comparison`,
    `accessibility_report`, and `accessibility_interpretation` are all
    nullable because each was added after rows without it already existed
    (one column set per agent's migration, as the graph grew) — new rows
    always set all of them together, in one graph run.
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
    # Storage key for the Production Analysis Agent's captured screenshot
    # (see app.integrations.storage) — same pattern as
    # Scan.production_screenshot_key.
    production_screenshot_key: Mapped[str | None] = mapped_column(nullable=True)
    # Visual Comparison Agent's deterministic pixel-diff result/image and
    # LLM judgment — same shapes as Scan.comparison_result/diff_image_key
    # and Review.result respectively.
    comparison_result: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    diff_image_key: Mapped[str | None] = mapped_column(nullable=True)
    visual_comparison: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    # Accessibility Agent's deterministic axe-core report and LLM triage —
    # no separate image key, unlike the other agents: nothing new gets
    # stored to the storage backend here.
    accessibility_report: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    accessibility_interpretation: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
