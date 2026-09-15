"""Record calls made per source per day against its daily licence budget.

A licence's daily budget must survive process restarts and be shared by every
worker, so counting calls in memory is not an option: it resets on every run
and cannot see what another worker already spent.

Revision ID: 0006_source_quota_usage
Revises: 0005_company_websites
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_source_quota_usage"
down_revision: str | None = "0005_company_websites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_quota_usage",
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("calls >= 0", name="ck_source_quota_usage_calls_not_negative"),
        sa.PrimaryKeyConstraint("source_key", "day", name="pk_source_quota_usage"),
    )


def downgrade() -> None:
    op.drop_table("source_quota_usage")
