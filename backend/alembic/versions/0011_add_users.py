"""Add users."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_add_users"
down_revision: str | None = "0010_provenance_retired_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
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
        sa.UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
        # Mirrors `normalize_email()`. See the comment on `User.__table_args__`.
        sa.CheckConstraint(
            r"normalized_email = lower(btrim(email, E' \t\n\r\f\v'))",
            name="ck_users_normalized_email",
        ),
    )


def downgrade() -> None:
    op.drop_table("users")
