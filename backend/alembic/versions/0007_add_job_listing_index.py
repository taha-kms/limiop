"""Index the listing order and drop the index it replaces."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_add_job_listing_index"
down_revision: str | None = "0006_add_job_fingerprint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LISTING_INDEX = "ix_jobs_status_published_at_id"
REPLACED_INDEX = "ix_jobs_status_published_at"


def upgrade() -> None:
    # The listing pages by keyset over `published_at DESC NULLS LAST, id DESC`.
    # An ascending index scanned backward yields nulls first, which is the wrong
    # end of the catalog, so the order has to be stored the way it is read.
    op.create_index(
        LISTING_INDEX,
        "jobs",
        ["status", sa.text("published_at DESC NULLS LAST"), sa.text("id DESC")],
        unique=False,
    )
    # Redundant now: the new index shares the leading columns and direction does
    # not restrict a range scan, so it serves everything the old one served.
    op.drop_index(REPLACED_INDEX, table_name="jobs")


def downgrade() -> None:
    op.create_index(REPLACED_INDEX, "jobs", ["status", "published_at"], unique=False)
    op.drop_index(LISTING_INDEX, table_name="jobs")
