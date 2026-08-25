"""Create the shared platform tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_platform_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("precedence", sa.SmallInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_job_sources"),
        sa.UniqueConstraint("key", name="uq_job_sources_key"),
    )
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_companies"),
    )
    op.create_index(
        "ix_companies_normalized_name",
        "companies",
        ["normalized_name"],
        unique=False,
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column(
            "workplace_type",
            sa.String(length=11),
            server_default="unspecified",
            nullable=False,
        ),
        sa.Column(
            "employment_type",
            sa.String(length=11),
            server_default="unspecified",
            nullable=False,
        ),
        sa.Column("application_url", sa.String(length=2048), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=7), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("match_key", sa.String(length=80), server_default="", nullable=False),
        sa.CheckConstraint(
            "workplace_type IN ('remote', 'hybrid', 'onsite', 'unspecified')",
            name="ck_jobs_workplace_type",
        ),
        sa.CheckConstraint(
            "employment_type IN ("
            "'full-time', 'part-time', 'contract', 'internship', 'temporary', 'unspecified'"
            ")",
            name="ck_jobs_employment_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'expired', 'removed')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint(
            "published_at IS NULL OR expires_at IS NULL OR expires_at >= published_at",
            name="ck_jobs_expiry_not_before_publication",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_jobs_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"], unique=False)
    op.create_index("ix_jobs_location", "jobs", ["location"], unique=False)
    op.create_index("ix_jobs_match_key", "jobs", ["match_key"], unique=False)
    op.create_index(
        "ix_jobs_status_expires_at",
        "jobs",
        ["status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_status_published_at_id",
        "jobs",
        ["status", sa.text("published_at DESC NULLS LAST"), sa.text("id DESC")],
        unique=False,
    )
    op.create_table(
        "job_provenance",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_job_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("raw_payload", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "last_seen_at >= first_seen_at",
            name="ck_job_provenance_seen_order",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_job_provenance_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["job_sources.id"],
            name="fk_job_provenance_source_id_job_sources",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_provenance"),
        sa.UniqueConstraint(
            "source_id",
            "source_job_id",
            name="uq_job_provenance_source_id_source_job_id",
        ),
    )
    op.create_index(
        "ix_job_provenance_job_id",
        "job_provenance",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_provenance_source_id_retired_at",
        "job_provenance",
        ["source_id", "retired_at"],
        unique=False,
    )
    op.create_table(
        "skill_concepts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("preferred_label", sa.String(length=255), nullable=False),
        sa.Column("esco_uri", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "length(btrim(preferred_label)) > 0",
            name="ck_skill_concepts_preferred_label_not_blank",
        ),
        sa.CheckConstraint(
            "esco_uri IS NULL OR length(btrim(esco_uri)) > 0",
            name="ck_skill_concepts_esco_uri_not_blank",
        ),
        sa.UniqueConstraint("esco_uri", name="uq_skill_concepts_esco_uri"),
    )
    op.create_table(
        "skill_alias_versions",
        sa.Column("version", sa.String(length=64), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "length(btrim(version)) > 0",
            name="ck_skill_alias_versions_version_not_blank",
        ),
    )
    op.create_table(
        "skill_surface_forms",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("alias_version", sa.String(length=64), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("surface_form", sa.String(length=255), nullable=False),
        sa.Column("normalized_form", sa.String(length=255), nullable=False),
        sa.CheckConstraint(
            "length(btrim(surface_form)) > 0",
            name="ck_skill_surface_forms_surface_form_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(normalized_form)) > 0",
            name="ck_skill_surface_forms_normalized_form_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["alias_version"],
            ["skill_alias_versions.version"],
            name="fk_skill_surface_forms_alias_version_skill_alias_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["skill_concepts.id"],
            name="fk_skill_surface_forms_concept_id_skill_concepts",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "alias_version",
            "normalized_form",
            "concept_id",
            name="uq_skill_surface_forms_version_form_concept",
        ),
    )


def downgrade() -> None:
    op.drop_table("skill_surface_forms")
    op.drop_table("skill_alias_versions")
    op.drop_table("skill_concepts")
    op.drop_index("ix_job_provenance_source_id_retired_at", table_name="job_provenance")
    op.drop_index("ix_job_provenance_job_id", table_name="job_provenance")
    op.drop_table("job_provenance")
    op.drop_index("ix_jobs_status_published_at_id", table_name="jobs")
    op.drop_index("ix_jobs_status_expires_at", table_name="jobs")
    op.drop_index("ix_jobs_match_key", table_name="jobs")
    op.drop_index("ix_jobs_location", table_name="jobs")
    op.drop_index("ix_jobs_company_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_companies_normalized_name", table_name="companies")
    op.drop_table("companies")
    op.drop_table("job_sources")
