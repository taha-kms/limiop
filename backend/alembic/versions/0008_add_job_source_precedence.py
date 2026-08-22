"""Rank sources against each other."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_add_job_source_precedence"
down_revision: str | None = "0007_add_job_listing_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Zero for everything already stored. One source cannot lose a disagreement
    # it has nobody to disagree with, so the existing catalogue is unaffected
    # until a second source is registered above it.
    op.add_column(
        "job_sources",
        sa.Column("precedence", sa.SmallInteger(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("job_sources", "precedence")
