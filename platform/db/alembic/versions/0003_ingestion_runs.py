"""Record one row per ingestion execution.

Revision ID: 0003_ingestion_runs
Revises: 0002_job_skills
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_ingestion_runs"
down_revision: str | None = "0002_job_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched", sa.Integer(), nullable=False),
        sa.Column("created", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("reached_the_end", sa.Boolean(), nullable=False),
        sa.Column("stopped_at_budget", sa.Boolean(), nullable=False),
        sa.Column("alias_version", sa.String(length=64), nullable=True),
        sa.Column("mentions_resolved", sa.Integer(), nullable=False),
        sa.Column("mentions_unknown", sa.Integer(), nullable=False),
        sa.Column("extraction_failed", sa.Integer(), nullable=False),
        sa.Column("failure_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "state IN ('running', 'completed', 'failed')",
            name="ck_ingestion_runs_state",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_ingestion_runs_timestamp_order",
        ),
        sa.CheckConstraint(
            "(state = 'running') = (finished_at IS NULL)",
            name="ck_ingestion_runs_finished_when_terminal",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_runs"),
    )
    op.create_index(
        "ix_ingestion_runs_source_key_started_at",
        "ingestion_runs",
        ["source_key", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_runs_source_key_started_at", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
