"""Rename the job fingerprint to what it now is, and retire the old values.

The stored value used to be an identity: employer, title, and location hashed
together, equal only for jobs that were the same posting. It is now a match key
that blocks candidates by employer and role, with the place and the description
deciding among them, so the name no longer described the thing.

The version prefix changes with the rules, so every stored value is stale. They
are cleared rather than recomputed, because recomputing needs the title
normalization that lives in the application and freezing a copy of it here
would leave two definitions to drift apart.

Between this migration and the next full run of each source, a posting arriving
from a second source will not match one already stored, and will be stored
again. Records match on provenance regardless, so each source repairs its own
rows on its next run. Nothing persistent holds a catalogue today, which is what
makes clearing acceptable; it would not be once one does.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_rename_to_match_key"
down_revision: str | None = "0008_add_job_source_precedence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_jobs_fingerprint", table_name="jobs")
    op.alter_column("jobs", "fingerprint", new_column_name="match_key")
    op.execute(sa.text("UPDATE jobs SET match_key = ''"))
    op.create_index("ix_jobs_match_key", "jobs", ["match_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_match_key", table_name="jobs")
    op.alter_column("jobs", "match_key", new_column_name="fingerprint")
    op.execute(sa.text("UPDATE jobs SET fingerprint = ''"))
    op.create_index("ix_jobs_fingerprint", "jobs", ["fingerprint"], unique=False)
