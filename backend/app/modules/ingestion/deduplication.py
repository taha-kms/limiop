"""Deciding whether an incoming job is already stored.

This service decides; it never writes. Applying a decision is #28's job, which
keeps the reasoning testable apart from the transaction that acts on it.

Two match paths are tried in order:

1. Provenance. `(source_id, source_job_id)` is the provider's own claim that
   this is the record we saw before, so it wins even when the job was renamed.
2. Identity. Used when the provider record is new to us but the posting may
   already have arrived from somewhere else. The match key blocks candidates by
   employer and role; place and text decide among them. Neither stage is
   sufficient alone, and `jobs.matching` explains why.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.matching import match_key, reads_the_same, same_place
from app.modules.jobs.models import Job, JobProvenance, JobSource
from app.modules.jobs.schemas import NormalizedJob


class MatchBasis(StrEnum):
    """How an incoming job was recognized."""

    PROVENANCE = "provenance"
    IDENTITY = "identity"


class DeduplicationOutcome(StrEnum):
    """What should happen to an incoming job."""

    NEW = "new"
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class DeduplicationDecision:
    """One decision about one incoming job.

    `job_id` names the canonical job to update, and is absent for `NEW` and for
    `AMBIGUOUS`, where `candidate_job_ids` lists what the match found instead.
    """

    outcome: DeduplicationOutcome
    match_key: str
    job_id: UUID | None = None
    matched_by: MatchBasis | None = None
    candidate_job_ids: tuple[UUID, ...] = ()


def has_material_change(stored: Job, incoming: NormalizedJob) -> bool:
    """Whether an incoming job says anything different from the stored one."""
    return (
        stored.title != incoming.title
        or stored.description != incoming.description
        or stored.location != incoming.location
        or stored.workplace_type != incoming.workplace_type
        or stored.employment_type != incoming.employment_type
        or stored.application_url != str(incoming.application_url)
        or stored.published_at != incoming.published_at
        or stored.expires_at != incoming.expires_at
    )


def compare(
    stored: Job,
    incoming: NormalizedJob,
    matched_by: MatchBasis,
    value: str,
) -> DeduplicationDecision:
    """Turn a matched job into a changed or unchanged decision."""
    outcome = (
        DeduplicationOutcome.CHANGED
        if has_material_change(stored, incoming)
        else DeduplicationOutcome.UNCHANGED
    )
    return DeduplicationDecision(
        outcome=outcome,
        match_key=value,
        job_id=stored.id,
        matched_by=matched_by,
    )


async def find_by_provenance(session: AsyncSession, incoming: NormalizedJob) -> Job | None:
    """Return the job this exact provider record already produced, if any."""
    statement = (
        select(Job)
        .join(JobProvenance, JobProvenance.job_id == Job.id)
        .join(JobSource, JobSource.id == JobProvenance.source_id)
        .where(
            JobSource.key == incoming.provenance.source_key,
            JobProvenance.source_job_id == incoming.provenance.source_job_id,
        )
    )
    return (await session.scalars(statement)).one_or_none()


async def find_by_match_key(session: AsyncSession, value: str) -> list[Job]:
    """Return every stored job for the same employer and role, oldest first."""
    statement = select(Job).where(Job.match_key == value).order_by(Job.created_at, Job.id)
    return list(await session.scalars(statement))


def describes_the_same_posting(stored: Job, incoming: NormalizedJob) -> bool:
    """Whether a candidate is this posting rather than a sibling of it.

    The key groups an employer's openings by role, and one employer runs the
    same role in several cities and sometimes several times in one city. The
    place separates the first case and the text separates the second.
    """
    return same_place(stored.location, incoming.location) and reads_the_same(
        stored.description, incoming.description
    )


async def decide(session: AsyncSession, incoming: NormalizedJob) -> DeduplicationDecision:
    """Decide what should happen to one incoming job."""
    value = match_key(incoming)

    # The provider's own claim that this is the record we saw before, so it wins
    # even when the posting was renamed out of its own key.
    known = await find_by_provenance(session, incoming)
    if known is not None:
        return compare(known, incoming, MatchBasis.PROVENANCE, value)

    blocked = await find_by_match_key(session, value)
    candidates = [job for job in blocked if describes_the_same_posting(job, incoming)]

    if not candidates:
        return DeduplicationDecision(outcome=DeduplicationOutcome.NEW, match_key=value)
    if len(candidates) > 1:
        # Several stored jobs are indistinguishable from this record. Refusing
        # to choose is the only safe answer: picking one would fold a distinct
        # posting into another and lose it.
        return DeduplicationDecision(
            outcome=DeduplicationOutcome.AMBIGUOUS,
            match_key=value,
            matched_by=MatchBasis.IDENTITY,
            candidate_job_ids=tuple(candidate.id for candidate in candidates),
        )
    return compare(candidates[0], incoming, MatchBasis.IDENTITY, value)
