"""Add candidate profiles."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_add_candidate_profiles"
down_revision: str | None = "0012_add_canonical_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_table("candidate_profiles")
