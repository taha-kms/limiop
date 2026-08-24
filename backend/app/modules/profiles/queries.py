"""Reusable readiness predicates for candidate-profile queries."""

from sqlalchemy import ColumnElement

from app.modules.profiles.models import CandidateProfile

# Structural only until #130 defines and measures what sufficient usable skill
# data means. Callers must count only skills that have already passed that gate.
PROVISIONAL_MINIMUM_USABLE_SKILLS = 1


def matching_ready(usable_skill_count: ColumnElement[int]) -> ColumnElement[bool]:
    """Whether a profile is complete and has enough future usable skill rows.

    The profile-skill table deliberately does not exist here. The owner of that
    table supplies a correlated count, keeping this query independent of #46
    while giving matching one canonical predicate to reuse.
    """
    return CandidateProfile.profile_complete.is_(True) & (
        usable_skill_count >= PROVISIONAL_MINIMUM_USABLE_SKILLS
    )
