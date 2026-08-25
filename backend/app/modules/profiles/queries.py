"""Reusable candidate-profile statements and readiness predicates."""

from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import contains_eager
from sqlalchemy.sql import Select

from app.modules.profiles.models import CandidateProfile, CandidateProfileSkill
from app.modules.skills.models import SkillConcept

# Every stored profile skill is currently a canonically resolved concept, so
# usable equals stored. The minimum remains provisional until #130 decides
# whether the unknown-skill gate will admit anything weaker.
PROVISIONAL_MINIMUM_USABLE_SKILLS = 1


def profile_skills_for_user(user_id: UUID) -> Select[tuple[CandidateProfileSkill]]:
    """Select one owner's skills with their canonical concepts loaded."""
    return (
        select(CandidateProfileSkill)
        .join(CandidateProfileSkill.profile)
        .join(CandidateProfileSkill.concept)
        .options(contains_eager(CandidateProfileSkill.concept))
        .where(CandidateProfile.user_id == user_id)
        .order_by(func.lower(SkillConcept.preferred_label), CandidateProfileSkill.concept_id)
    )


def matching_ready() -> ColumnElement[bool]:
    """Whether a profile is complete and has a canonical stored skill.

    The scalar subquery is correlated to whichever ``CandidateProfile`` row the
    caller is selecting, so the predicate cannot accidentally count another
    candidate's skills.
    """
    stored_skill_count = (
        select(func.count())
        .select_from(CandidateProfileSkill)
        .where(CandidateProfileSkill.profile_id == CandidateProfile.id)
        .correlate(CandidateProfile)
        .scalar_subquery()
    )
    return CandidateProfile.profile_complete.is_(True) & (
        stored_skill_count >= PROVISIONAL_MINIMUM_USABLE_SKILLS
    )
