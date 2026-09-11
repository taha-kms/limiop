"""Add the automatic board registry table.

The switch from a hard-coded board list to a database registry must not stop
anything already running, so this migration also seeds Greenhouse's three
shipped boards, pinned and confirmed, exactly as they poll today.

Revision ID: 0004_job_boards
Revises: 0003_ingestion_runs
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_job_boards"
down_revision: str | None = "0003_ingestion_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHIPPED_GREENHOUSE_BOARDS = ("anthropic", "datadog", "hudl")


def upgrade() -> None:
    op.create_table(
        "job_boards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=13),
            server_default="candidate",
            nullable=False,
        ),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_posting_count", sa.Integer(), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "pinned",
            sa.Boolean(),
            server_default=sa.text("false"),
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
            "status IN ("
            "'candidate','confirmed','named','wrong_company',"
            "'not_found','unreachable','inactive','blocked'"
            ")",
            name="ck_job_boards_status",
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0",
            name="ck_job_boards_failures_not_negative",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["job_sources.id"],
            name="fk_job_boards_source_id_job_sources",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_job_boards_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_boards"),
        sa.UniqueConstraint("source_id", "slug", name="uq_job_boards_source_id_slug"),
    )
    op.create_index(
        "ix_job_boards_source_id_status",
        "job_boards",
        ["source_id", "status"],
    )
    op.create_index("ix_job_boards_company_id", "job_boards", ["company_id"])

    # Greenhouse's source row may not exist on a fresh database; insert it
    # idempotently before seeding its boards.
    op.execute(
        sa.text(
            """
            INSERT INTO job_sources (id, key, display_name, base_url, precedence)
            VALUES (gen_random_uuid(), 'greenhouse', 'Greenhouse',
                    'https://boards-api.greenhouse.io/v1/boards', 20)
            ON CONFLICT ON CONSTRAINT uq_job_sources_key DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO job_boards (id, source_id, slug, status, evidence, pinned, verified_at)
            SELECT gen_random_uuid(), s.id, b.slug, 'confirmed',
                   jsonb_build_object(
                       'kind', 'operator',
                       'note', 'seeded from the shipped board list',
                       'checked_at', now()
                   ),
                   true, now()
            FROM job_sources s
            CROSS JOIN (VALUES ('anthropic'), ('datadog'), ('hudl')) AS b(slug)
            WHERE s.key = 'greenhouse'
            ON CONFLICT ON CONSTRAINT uq_job_boards_source_id_slug DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_job_boards_company_id", table_name="job_boards")
    op.drop_index("ix_job_boards_source_id_status", table_name="job_boards")
    op.drop_table("job_boards")
    # The job_sources row for Greenhouse is left in place: it is what
    # ingestion would create on its next run anyway.
