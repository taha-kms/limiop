"""Add user-owned CV metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_add_cvs"
down_revision: str | None = "0013_add_candidate_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cvs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "processing_state",
            sa.String(length=10),
            server_default="pending",
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
            "storage_key <> '' AND storage_key = btrim(storage_key)",
            name="ck_cvs_storage_key_nonblank",
        ),
        sa.CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_cvs_checksum_sha256",
        ),
        sa.CheckConstraint(
            "media_type = 'application/pdf'",
            name="ck_cvs_media_type",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_cvs_size_bytes_positive"),
        sa.CheckConstraint(
            "processing_state IN ('pending', 'processing', 'processed', 'failed')",
            name="ck_cvs_processing_state",
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_cvs_timestamp_order"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="fk_cvs_owner_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cvs"),
        sa.UniqueConstraint("storage_key", name="uq_cvs_storage_key"),
    )
    op.create_index("ix_cvs_owner_id", "cvs", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cvs_owner_id", table_name="cvs")
    op.drop_table("cvs")
