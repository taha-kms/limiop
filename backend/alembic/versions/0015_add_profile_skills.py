"""Add canonical skills selected for candidate profiles."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_add_profile_skills"
down_revision: str | None = "0014_add_cvs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_profile_skills",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("vocabulary_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "length(btrim(vocabulary_version)) > 0",
            name="ck_candidate_profile_skills_vocabulary_version_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["candidate_profiles.id"],
            name="fk_candidate_profile_skills_profile_id_candidate_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["skill_concepts.id"],
            name="fk_candidate_profile_skills_concept_id_skill_concepts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "profile_id",
            "concept_id",
            name="pk_candidate_profile_skills",
        ),
    )
    op.create_index(
        "ix_candidate_profile_skills_concept_id",
        "candidate_profile_skills",
        ["concept_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_profile_skills_concept_id",
        table_name="candidate_profile_skills",
    )
    op.drop_table("candidate_profile_skills")
