"""Add the canonical jobs table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_jobs"
down_revision: str | None = "0003_add_companies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
        sa.Column(
            "status",
            sa.String(length=7),
            server_default="active",
            nullable=False,
        ),
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
    op.create_index(
        "ix_jobs_status_expires_at",
        "jobs",
        ["status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_status_published_at",
        "jobs",
        ["status", "published_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_status_published_at", table_name="jobs")
    op.drop_index("ix_jobs_status_expires_at", table_name="jobs")
    op.drop_index("ix_jobs_location", table_name="jobs")
    op.drop_index("ix_jobs_company_id", table_name="jobs")
    op.drop_table("jobs")
