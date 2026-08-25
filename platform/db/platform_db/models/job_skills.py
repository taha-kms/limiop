"""Persistence models for skills extracted from job postings."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_db.base import Base
from platform_db.models.skills import SURFACE_FORM_LENGTH, VOCABULARY_VERSION_LENGTH

if TYPE_CHECKING:
    from platform_db.models.catalog import Job
    from platform_db.models.skills import SkillAliasVersion, SkillConcept

EXTRACTOR_VERSION_LENGTH = 64


class JobSkill(Base):
    """A canonical skill resolved from one job posting."""

    __tablename__ = "job_skills"
    __table_args__ = (
        PrimaryKeyConstraint(
            "job_id",
            "concept_id",
            name="pk_job_skills",
        ),
    )

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "jobs.id",
            name="fk_job_skills_job_id_jobs",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    concept_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "skill_concepts.id",
            name="fk_job_skills_concept_id_skill_concepts",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    alias_version: Mapped[str] = mapped_column(
        ForeignKey(
            "skill_alias_versions.version",
            name="fk_job_skills_alias_version_skill_alias_versions",
        ),
        nullable=False,
    )
    surface_form: Mapped[str] = mapped_column(String(SURFACE_FORM_LENGTH), nullable=False)
    job: Mapped["Job"] = relationship()
    concept: Mapped["SkillConcept"] = relationship()
    alias_version_record: Mapped["SkillAliasVersion"] = relationship()


class JobSkillMention(Base):
    """An unresolved skill mention observed in one job posting."""

    __tablename__ = "job_skill_mentions"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "surface_form",
            "extractor_version",
            "alias_version",
            name="uq_job_skill_mentions_job_surface_extractor_alias",
        ),
        Index("ix_job_skill_mentions_normalized_form", "normalized_form"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "jobs.id",
            name="fk_job_skill_mentions_job_id_jobs",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    surface_form: Mapped[str] = mapped_column(String(SURFACE_FORM_LENGTH), nullable=False)
    normalized_form: Mapped[str | None] = mapped_column(
        String(SURFACE_FORM_LENGTH),
        nullable=True,
    )
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extractor_version: Mapped[str] = mapped_column(
        String(EXTRACTOR_VERSION_LENGTH),
        nullable=False,
    )
    alias_version: Mapped[str] = mapped_column(
        ForeignKey(
            "skill_alias_versions.version",
            name="fk_job_skill_mentions_alias_version_skill_alias_versions",
        ),
        nullable=False,
    )
    evidence: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    job: Mapped["Job"] = relationship()
    alias_version_record: Mapped["SkillAliasVersion"] = relationship()
