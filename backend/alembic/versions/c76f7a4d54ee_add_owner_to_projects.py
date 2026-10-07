"""add owner to projects

Revision ID: c76f7a4d54ee
Revises: a2694a5d1758
Create Date: 2026-10-06

Added nullable, backfilled, then made NOT NULL. A plain non-nullable add
would fail on any database that already has projects — which is every
developer's, since projects predate accounts.

The backfill assigns existing projects to the oldest account, which in a
local database is the developer who created them. Nothing is deleted: if
that guess is wrong the row is still there to reassign. A database with
projects but no users at all can't name an owner, so the migration stops
and says so rather than inventing a user or dropping the rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c76f7a4d54ee"
down_revision: str | Sequence[str] | None = "a2694a5d1758"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("owner_id", sa.UUID(), nullable=True))

    connection = op.get_bind()
    orphans = connection.execute(sa.text("SELECT count(*) FROM projects")).scalar_one()
    if orphans:
        oldest_user = connection.execute(
            sa.text("SELECT id FROM users ORDER BY created_at LIMIT 1")
        ).scalar_one_or_none()
        if oldest_user is None:
            raise RuntimeError(
                f"{orphans} project(s) exist but there are no users to own them. "
                "Sign up first (POST /api/v1/auth/signup), then re-run this migration — "
                "the projects will be assigned to that account."
            )
        connection.execute(
            sa.text("UPDATE projects SET owner_id = :owner WHERE owner_id IS NULL"),
            {"owner": oldest_user},
        )

    op.alter_column("projects", "owner_id", nullable=False)
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"])
    op.create_foreign_key(
        "fk_projects_owner_id_users",
        "projects",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_owner_id_users", "projects", type_="foreignkey")
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_column("projects", "owner_id")
