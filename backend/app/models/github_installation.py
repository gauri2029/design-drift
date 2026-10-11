import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GitHubInstallation(Base):
    """A GitHub App installation a user has linked to their account.

    Holds no credentials. Access tokens are minted per request from the
    App's private key and discarded (see app.integrations.github.client), so
    this row is only a statement that *this user* proved they administer
    *this installation* — which is what every later repository call is
    authorized against.
    """

    __tablename__ = "github_installations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # GitHub's own id. BigInteger because it is not bounded by int32, and
    # unique because one installation belongs to one account — a second user
    # claiming it is exactly the attack the uniqueness prevents.
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    # The org or user it is installed on, shown in the picker so someone
    # with several installations can tell them apart.
    account_login: Mapped[str] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
