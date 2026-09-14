"""Record where a company's website came from.

Resolution reads at most three keyless strategies (the catalogue's own
`website_url`, domains mentioned in stored postings, Wikidata) and needs
somewhere to note which one answered and when it last tried, so a company
with no findable website is not retried every run.

Revision ID: 0005_company_websites
Revises: 0004_job_boards
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_company_websites"
down_revision: str | None = "0004_job_boards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("website_source", sa.String(length=32), nullable=True))
    op.add_column(
        "companies",
        sa.Column("website_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "website_checked_at")
    op.drop_column("companies", "website_source")
