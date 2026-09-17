"""Record on the job itself when retention anonymised it.

Retention strips a withdrawn job that user data still references rather than
deleting it, and must not strip it again on every pass. The marker used to be
a key in each provenance payload, but a source re-listing the job rewrites
only the payload it owns, so a job with two sources came back with one marker
and full content and was never a candidate again. A fact about the job lives
on the job.

Revision ID: 0007_job_anonymised_at
Revises: 0006_source_quota_usage
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_job_anonymised_at"
down_revision: str | None = "0006_source_quota_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("anonymised_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "anonymised_at")
