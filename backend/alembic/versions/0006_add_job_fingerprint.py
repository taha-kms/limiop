"""Add the canonical job fingerprint."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_add_job_fingerprint"
down_revision: str | None = "0005_add_job_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FINGERPRINT_LENGTH = 80


def upgrade() -> None:
    # The empty server default only exists so the column can be added to a
    # populated table. Real fingerprints are prefixed with a version, so an
    # empty value never matches a lookup and cannot merge unrelated jobs.
    op.add_column(
        "jobs",
        sa.Column(
            "fingerprint",
            sa.String(length=FINGERPRINT_LENGTH),
            server_default="",
            nullable=False,
        ),
    )
    op.create_index("ix_jobs_fingerprint", "jobs", ["fingerprint"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_fingerprint", table_name="jobs")
    op.drop_column("jobs", "fingerprint")
