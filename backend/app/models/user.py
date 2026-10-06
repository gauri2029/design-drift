import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """An account that can sign in to Design Drift.

    Deliberately not an owner of anything yet: projects, scans and reviews
    carry no user_id, so signing in gates access to the app rather than
    partitioning its data. Per-user ownership is a separate change — adding
    it here first would mean a column nothing reads.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Stored lowercased by the service layer, so "A@b.com" and "a@b.com"
    # cannot become two accounts.
    email: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    # An argon2 hash, never a password. Named for what it holds so no caller
    # can mistake it for something comparable with ==.
    password_hash: Mapped[str] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
