"""clear superseded code_analysis results

Data-only. The Code Analysis Agent's output schema changed shape when it
gained content search: `locations[].candidate_files` (a list of guessed
file paths) became `locations[].location` (one exact file/line range with
quoted evidence), plus the new `no_match` and `explanation` fields.

Rows written by the older, paths-only version can't satisfy the new
required fields, so `DesignAnalysisRead` would fail to validate them on
read — a stored row would break the list endpoint for its whole project.
Clearing them is the honest fix: those results were guesses from filenames
alone, they can't be back-filled into the richer shape, and every other
column on the row (the analyses, the comparison, the findings) is
untouched and still valid. Re-running the workflow regenerates this field.

Revision ID: e9edcbbce631
Revises: a7505a6aa4dc
Create Date: 2026-08-19 20:41:00.875733

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9edcbbce631"
down_revision: str | Sequence[str] | None = "a7505a6aa4dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Clear code_analysis values written in the pre-content-search shape."""
    op.execute(
        sa.text("UPDATE design_analyses SET code_analysis = NULL WHERE code_analysis IS NOT NULL")
    )


def downgrade() -> None:
    """Irreversible: the cleared values were not copied anywhere.

    A no-op rather than an error, so rolling back past this point still
    works — the column itself is dropped by the previous revision, and a
    null column needs nothing undone.
    """
