"""Loading the two skill sets a match is computed from.

Only jobs sharing at least one concept with the candidate are read. Everything
else scores zero by construction, and reading the whole catalogue to discover
that would be a table scan whose answer is always the same.
"""

from uuid import UUID

from platform_db.models import Job, SkillConcept
from platform_db.models.catalog import JobStatus
from platform_db.models.job_skills import JobSkill
from sqlalchemy import Select, select
from sqlalchemy.orm import joinedload

from app.modules.profiles.models import CandidateProfile, CandidateProfileSkill


def candidate_concepts(user_id: UUID) -> Select[tuple[UUID]]:
    """The canonical concepts on one candidate's profile."""
    return (
        select(CandidateProfileSkill.concept_id)
        .join(CandidateProfileSkill.profile)
        .where(CandidateProfile.user_id == user_id)
    )


def scorable_jobs(concepts: set[UUID]) -> Select[tuple[Job]]:
    """Active jobs sharing at least one concept with the candidate.

    Status is not a filter a caller may turn off, exactly as on the public
    listing: a posting nobody can apply to is not a match.
    """
    sharing = select(JobSkill.job_id).where(JobSkill.concept_id.in_(concepts)).distinct()
    return (
        select(Job)
        .options(joinedload(Job.company))
        .where(Job.status == JobStatus.ACTIVE, Job.id.in_(sharing))
    )


def job_concepts(job_ids: list[UUID]) -> Select[tuple[UUID, UUID]]:
    """Every required concept of the given jobs, as (job id, concept id)."""
    return select(JobSkill.job_id, JobSkill.concept_id).where(JobSkill.job_id.in_(job_ids))


def concept_labels(concepts: set[UUID]) -> Select[tuple[UUID, str]]:
    """The names to show for a set of concepts.

    A matched skill a candidate cannot see named is not an explanation, so the
    labels are read rather than the identifiers being served raw.
    """
    return select(SkillConcept.id, SkillConcept.preferred_label).where(
        SkillConcept.id.in_(concepts)
    )
