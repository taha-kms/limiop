"""Persistence models for canonical skills and their versioned aliases."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_db.base import Base

CONCEPT_LABEL_LENGTH = 255
ESCO_URI_LENGTH = 2048
SURFACE_FORM_LENGTH = 255
VOCABULARY_VERSION_LENGTH = 64


class SkillConcept(Base):
    """A stable skill identity whose label and mappings may evolve."""

    __tablename__ = "skill_concepts"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(preferred_label)) > 0",
            name="ck_skill_concepts_preferred_label_not_blank",
        ),
        CheckConstraint(
            "esco_uri IS NULL OR length(btrim(esco_uri)) > 0",
            name="ck_skill_concepts_esco_uri_not_blank",
        ),
        UniqueConstraint("esco_uri", name="uq_skill_concepts_esco_uri"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    preferred_label: Mapped[str] = mapped_column(String(CONCEPT_LABEL_LENGTH), nullable=False)
    esco_uri: Mapped[str | None] = mapped_column(String(ESCO_URI_LENGTH), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    surface_forms: Mapped[list["SkillSurfaceForm"]] = relationship(back_populates="concept")


class SkillAliasVersion(Base):
    """One immutable, reviewable release of the known-skill alias table."""

    __tablename__ = "skill_alias_versions"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(version)) > 0",
            name="ck_skill_alias_versions_version_not_blank",
        ),
    )

    version: Mapped[str] = mapped_column(String(VOCABULARY_VERSION_LENGTH), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    surface_forms: Mapped[list["SkillSurfaceForm"]] = relationship(
        back_populates="alias_version_record"
    )


class SkillSurfaceForm(Base):
    """A spelling or phrase that names a concept in one alias-table version.

    More than one row may share a normalized form when the term is genuinely
    ambiguous. The known-skill resolver reports that ambiguity rather than
    choosing one concept silently.
    """

    __tablename__ = "skill_surface_forms"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(surface_form)) > 0",
            name="ck_skill_surface_forms_surface_form_not_blank",
        ),
        CheckConstraint(
            "length(btrim(normalized_form)) > 0",
            name="ck_skill_surface_forms_normalized_form_not_blank",
        ),
        UniqueConstraint(
            "alias_version",
            "normalized_form",
            "concept_id",
            name="uq_skill_surface_forms_version_form_concept",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    alias_version: Mapped[str] = mapped_column(
        ForeignKey(
            "skill_alias_versions.version",
            name="fk_skill_surface_forms_alias_version_skill_alias_versions",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    concept_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "skill_concepts.id",
            name="fk_skill_surface_forms_concept_id_skill_concepts",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    surface_form: Mapped[str] = mapped_column(String(SURFACE_FORM_LENGTH), nullable=False)
    normalized_form: Mapped[str] = mapped_column(String(SURFACE_FORM_LENGTH), nullable=False)
    concept: Mapped[SkillConcept] = relationship(back_populates="surface_forms")
    alias_version_record: Mapped[SkillAliasVersion] = relationship(back_populates="surface_forms")
