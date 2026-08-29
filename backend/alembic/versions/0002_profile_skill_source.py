"""Record how each profile skill reached the profile.

Existing rows are all hand-picked: the skill picker was the only writer before
this. `manual` is therefore the correct backfill as well as the correct
default, and re-reading a CV can now replace what the last read wrote without
touching what the candidate chose.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_profile_skill_source"
down_revision: str | None = "0001_backend_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_CONSTRAINT = "ck_candidate_profile_skills_source"


def upgrade() -> None:
    op.add_column(
        "candidate_profile_skills",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="manual",
        ),
    )
    op.create_check_constraint(
        SOURCE_CONSTRAINT,
        "candidate_profile_skills",
        "source IN ('manual', 'cv')",
    )


def downgrade() -> None:
    op.drop_constraint(SOURCE_CONSTRAINT, "candidate_profile_skills", type_="check")
    op.drop_column("candidate_profile_skills", "source")
