"""Persistence for the canonical candidate profile."""

from datetime import datetime
from uuid import UUID, uuid4

from platform_db.base import Base
from platform_db.models import SkillConcept
from platform_db.models.skills import VOCABULARY_VERSION_LENGTH
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.accounts.models import User
from app.modules.jobs.domain import EmploymentType, WorkplaceType

PROFILE_COMPLETE_SQL = """
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
"""


class CandidateProfile(Base):
    """The one candidate description owned by an account.

    Every field may start absent so either onboarding route can save partial
    progress. PostgreSQL derives whether the required subset is complete.
    """

    __tablename__ = "candidate_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_candidate_profiles_user_id"),
        CheckConstraint(
            "workplace_types IS NULL OR workplace_types <@ "
            "ARRAY['remote', 'hybrid', 'onsite', 'unspecified']::varchar[]",
            name="ck_candidate_profiles_workplace_types",
        ),
        CheckConstraint(
            "employment_types IS NULL OR employment_types <@ "
            "ARRAY['full-time', 'part-time', 'contract', 'internship', "
            "'temporary', 'unspecified']::varchar[]",
            name="ck_candidate_profiles_employment_types",
        ),
        CheckConstraint(
            "years_experience IS NULL OR years_experience >= 0",
            name="ck_candidate_profiles_years_experience_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_candidate_profiles_user_id_users",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workplace_types: Mapped[list[WorkplaceType] | None] = mapped_column(
        ARRAY(
            Enum(
                WorkplaceType,
                name="candidate_workplace_type",
                native_enum=False,
                create_constraint=False,
                validate_strings=True,
                values_callable=lambda members: [member.value for member in members],
            )
        ),
        nullable=True,
    )
    employment_types: Mapped[list[EmploymentType] | None] = mapped_column(
        ARRAY(
            Enum(
                EmploymentType,
                name="candidate_employment_type",
                native_enum=False,
                create_constraint=False,
                validate_strings=True,
                values_callable=lambda members: [member.value for member in members],
            )
        ),
        nullable=True,
    )
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_complete: Mapped[bool] = mapped_column(
        Boolean,
        Computed(PROFILE_COMPLETE_SQL, persisted=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    user: Mapped[User] = relationship()
    skills: Mapped[list["CandidateProfileSkill"]] = relationship(
        back_populates="profile",
        passive_deletes=True,
    )


class CandidateProfileSkill(Base):
    """A canonical skill selected for one candidate profile."""

    __tablename__ = "candidate_profile_skills"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(vocabulary_version)) > 0",
            name="ck_candidate_profile_skills_vocabulary_version_not_blank",
        ),
        PrimaryKeyConstraint(
            "profile_id",
            "concept_id",
            name="pk_candidate_profile_skills",
        ),
    )

    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "candidate_profiles.id",
            name="fk_candidate_profile_skills_profile_id_candidate_profiles",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    concept_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "skill_concepts.id",
            name="fk_candidate_profile_skills_concept_id_skill_concepts",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    vocabulary_version: Mapped[str] = mapped_column(
        String(VOCABULARY_VERSION_LENGTH), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    profile: Mapped[CandidateProfile] = relationship(back_populates="skills")
    concept: Mapped[SkillConcept] = relationship()
