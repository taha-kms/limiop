"""Add job skills and unresolved skill mentions.

Revision ID: 0002_job_skills
Revises: 0001_platform_baseline
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_job_skills"
down_revision: str | None = "0001_platform_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_skills",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("alias_version", sa.String(length=64), nullable=False),
        sa.Column("surface_form", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["alias_version"],
            ["skill_alias_versions.version"],
            name="fk_job_skills_alias_version_skill_alias_versions",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["skill_concepts.id"],
            name="fk_job_skills_concept_id_skill_concepts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_job_skills_job_id_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", "concept_id", name="pk_job_skills"),
    )
    op.create_table(
        "job_skill_mentions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("surface_form", sa.String(length=255), nullable=False),
        sa.Column("normalized_form", sa.String(length=255), nullable=True),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("alias_version", sa.String(length=64), nullable=False),
        sa.Column("evidence", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["alias_version"],
            ["skill_alias_versions.version"],
            name="fk_job_skill_mentions_alias_version_skill_alias_versions",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_job_skill_mentions_job_id_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_skill_mentions"),
        sa.UniqueConstraint(
            "job_id",
            "surface_form",
            "extractor_version",
            "alias_version",
            name="uq_job_skill_mentions_job_surface_extractor_alias",
        ),
    )
    op.create_index(
        "ix_job_skill_mentions_normalized_form",
        "job_skill_mentions",
        ["normalized_form"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_skill_mentions_normalized_form",
        table_name="job_skill_mentions",
    )
    op.drop_table("job_skill_mentions")
    op.drop_table("job_skills")
