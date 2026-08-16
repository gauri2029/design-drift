import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Scan(Base):
    """A single comparison run for a project: a fresh production screenshot
    diffed against the Figma render already stored on the project.

    `comparison_result` mirrors
    app.integrations.imaging.types.ComparisonResult exactly (see that
    model's docstring — a raw pixel-mismatch percentage, not a design
    fidelity score). Stored as JSONB rather than flat columns, matching
    Project.figma_data: it's a small fixed-shape record today, but there's
    no query/filter need yet that would justify promoting it to real
    columns (docs/principles.md #1).
    """

    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    viewport_width: Mapped[int] = mapped_column(nullable=False)
    viewport_height: Mapped[int] = mapped_column(nullable=False)

    # Storage keys (see app.integrations.storage) for the production
    # screenshot and the diff visualization. The Figma reference image is
    # not duplicated here — it's already on the project.
    production_screenshot_key: Mapped[str] = mapped_column(nullable=False)
    diff_image_key: Mapped[str] = mapped_column(nullable=False)
    comparison_result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
