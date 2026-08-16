import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    """A registered Design Drift project: a Figma design node + a target app URL.

    `figma_data` and `figma_screenshot_key` are populated once the Figma
    fetch has run (Phase 1 registration flow); they're nullable so a project
    can be created before that fetch completes.
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(nullable=False)

    figma_file_key: Mapped[str] = mapped_column(nullable=False)
    figma_node_id: Mapped[str] = mapped_column(nullable=False)
    target_url: Mapped[str] = mapped_column(nullable=False)
    # CSS selector on `target_url` that corresponds to the Figma node above.
    # Optional: if unset, a scan screenshots the full page instead — fine
    # for a whole-page Figma frame, less meaningful for a single component.
    target_selector: Mapped[str | None] = mapped_column(nullable=True)

    # Raw-ish node data from the Figma API (name, styles, layout, hierarchy),
    # serialized from app.integrations.figma.types.FigmaNode.
    figma_data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    # Storage key (see app.integrations.storage) for the rendered node image.
    figma_screenshot_key: Mapped[str | None] = mapped_column(nullable=True)
    figma_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
