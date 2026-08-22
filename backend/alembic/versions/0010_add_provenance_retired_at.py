"""Record when a source stopped listing a posting."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_provenance_retired_at"
down_revision: str | None = "0009_rename_to_match_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Null for everything already stored: no run has ever concluded a posting
    # was gone, so nothing may be treated as though one had.
    op.add_column(
        "job_provenance",
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_job_provenance_source_id_retired_at",
        "job_provenance",
        ["source_id", "retired_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_provenance_source_id_retired_at", table_name="job_provenance")
    op.drop_column("job_provenance", "retired_at")
