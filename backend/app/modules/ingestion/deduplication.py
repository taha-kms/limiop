"""Deciding whether an incoming job is already stored.

This service decides; it never writes. Applying a decision is #28's job, which
keeps the reasoning testable apart from the transaction that acts on it.

Two match paths are tried in order:

1. Provenance. `(source_id, source_job_id)` is the provider's own claim that
   this is the record we saw before, so it wins even when the job was renamed.
2. Fingerprint. A canonical identity match, used when the provider record is
   new to us but the posting may already have arrived from somewhere else.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.fingerprint import fingerprint
from app.modules.jobs.models import Job, JobProvenance, JobSource
from app.modules.jobs.schemas import NormalizedJob


class MatchBasis(StrEnum):
    """How an incoming job was recognized."""

    PROVENANCE = "provenance"
    FINGERPRINT = "fingerprint"


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
    fingerprint: str
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
        fingerprint=value,
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


async def find_by_fingerprint(session: AsyncSession, value: str) -> list[Job]:
    """Return every stored job sharing a canonical identity, oldest first."""
    statement = select(Job).where(Job.fingerprint == value).order_by(Job.created_at, Job.id)
    return list(await session.scalars(statement))


async def decide(session: AsyncSession, incoming: NormalizedJob) -> DeduplicationDecision:
    """Decide what should happen to one incoming job."""
    value = fingerprint(incoming)

    known = await find_by_provenance(session, incoming)
    if known is not None:
        return compare(known, incoming, MatchBasis.PROVENANCE, value)

    candidates = await find_by_fingerprint(session, value)
    if not candidates:
        return DeduplicationDecision(outcome=DeduplicationOutcome.NEW, fingerprint=value)
    if len(candidates) > 1:
        return DeduplicationDecision(
            outcome=DeduplicationOutcome.AMBIGUOUS,
            fingerprint=value,
            matched_by=MatchBasis.FINGERPRINT,
            candidate_job_ids=tuple(candidate.id for candidate in candidates),
        )
    return compare(candidates[0], incoming, MatchBasis.FINGERPRINT, value)
