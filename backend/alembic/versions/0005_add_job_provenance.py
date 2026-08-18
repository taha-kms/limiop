"""Add job provenance persistence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_add_job_provenance"
down_revision: str | None = "0004_add_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
        sa.Column(
            "raw_payload",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
        ),
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


def downgrade() -> None:
    op.drop_index("ix_job_provenance_job_id", table_name="job_provenance")
    op.drop_table("job_provenance")
