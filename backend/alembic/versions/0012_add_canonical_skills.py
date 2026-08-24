"""Add canonical skills and versioned surface forms."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_add_canonical_skills"
down_revision: str | None = "0011_add_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skill_concepts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("preferred_label", sa.String(length=255), nullable=False),
        sa.Column("esco_uri", sa.String(length=2048), nullable=True),
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
            "length(btrim(preferred_label)) > 0",
            name="ck_skill_concepts_preferred_label_not_blank",
        ),
        sa.CheckConstraint(
            "esco_uri IS NULL OR length(btrim(esco_uri)) > 0",
            name="ck_skill_concepts_esco_uri_not_blank",
        ),
        sa.UniqueConstraint("esco_uri", name="uq_skill_concepts_esco_uri"),
    )
    op.create_table(
        "skill_alias_versions",
        sa.Column("version", sa.String(length=64), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "length(btrim(version)) > 0",
            name="ck_skill_alias_versions_version_not_blank",
        ),
    )
    op.create_table(
        "skill_surface_forms",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("alias_version", sa.String(length=64), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("surface_form", sa.String(length=255), nullable=False),
        sa.Column("normalized_form", sa.String(length=255), nullable=False),
        sa.CheckConstraint(
            "length(btrim(surface_form)) > 0",
            name="ck_skill_surface_forms_surface_form_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(normalized_form)) > 0",
            name="ck_skill_surface_forms_normalized_form_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["alias_version"],
            ["skill_alias_versions.version"],
            name="fk_skill_surface_forms_alias_version_skill_alias_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["skill_concepts.id"],
            name="fk_skill_surface_forms_concept_id_skill_concepts",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "alias_version",
            "normalized_form",
            "concept_id",
            name="uq_skill_surface_forms_version_form_concept",
        ),
    )


def downgrade() -> None:
    op.drop_table("skill_surface_forms")
    op.drop_table("skill_alias_versions")
    op.drop_table("skill_concepts")
