"""Create the backend-owned tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_backend_baseline"
down_revision: str | None = None
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
        sa.CheckConstraint(
            r"normalized_email = lower(btrim(email, E' \t\n\r\f\v'))",
            name="ck_users_normalized_email",
        ),
    )
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("workplace_types", sa.ARRAY(sa.String(length=11)), nullable=True),
        sa.Column("employment_types", sa.ARRAY(sa.String(length=11)), nullable=True),
        sa.Column("headline", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column(
            "profile_complete",
            sa.Boolean(),
            sa.Computed(
                """
                display_name IS NOT NULL
                AND btrim(display_name) <> ''
                AND location IS NOT NULL
                AND btrim(location) <> ''
                AND workplace_types IS NOT NULL
                AND workplace_types && ARRAY['remote', 'hybrid', 'onsite']::varchar[]
                AND employment_types IS NOT NULL
                AND employment_types && ARRAY[
                    'full-time', 'part-time', 'contract', 'internship', 'temporary'
                ]::varchar[]
                """,
                persisted=True,
            ),
            nullable=False,
        ),
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
            "workplace_types IS NULL OR workplace_types <@ "
            "ARRAY['remote', 'hybrid', 'onsite', 'unspecified']::varchar[]",
            name="ck_candidate_profiles_workplace_types",
        ),
        sa.CheckConstraint(
            "employment_types IS NULL OR employment_types <@ "
            "ARRAY['full-time', 'part-time', 'contract', 'internship', "
            "'temporary', 'unspecified']::varchar[]",
            name="ck_candidate_profiles_employment_types",
        ),
        sa.CheckConstraint(
            "years_experience IS NULL OR years_experience >= 0",
            name="ck_candidate_profiles_years_experience_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_candidate_profiles_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", name="uq_candidate_profiles_user_id"),
    )
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
        sa.CheckConstraint("media_type = 'application/pdf'", name="ck_cvs_media_type"),
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
    op.create_table(
        "candidate_profile_skills",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("vocabulary_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "length(btrim(vocabulary_version)) > 0",
            name="ck_candidate_profile_skills_vocabulary_version_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["candidate_profiles.id"],
            name="fk_candidate_profile_skills_profile_id_candidate_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["skill_concepts.id"],
            name="fk_candidate_profile_skills_concept_id_skill_concepts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "profile_id",
            "concept_id",
            name="pk_candidate_profile_skills",
        ),
    )
    op.create_index(
        "ix_candidate_profile_skills_concept_id",
        "candidate_profile_skills",
        ["concept_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_profile_skills_concept_id",
        table_name="candidate_profile_skills",
    )
    op.drop_table("candidate_profile_skills")
    op.drop_index("ix_cvs_owner_id", table_name="cvs")
    op.drop_table("cvs")
    op.drop_table("candidate_profiles")
    op.drop_table("users")
