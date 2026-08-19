"""Applying one deduplication decision to the database.

Each record is written inside a savepoint. A record that violates a constraint
rolls back only itself, so one bad posting cannot discard the batch it arrived
with, and a caller can keep using the same session afterwards.

The service writes; it does not decide. Whether a job is new, changed, or
already known comes from `deduplication.decide`.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ingestion.contracts import IngestionStage, RecordFailure, RecordOutcome
from app.modules.ingestion.deduplication import DeduplicationOutcome, decide
from app.modules.jobs.domain import normalize_company_name
from app.modules.jobs.models import Company, Job, JobSource
from app.modules.jobs.repositories import observe_job_provenance
from app.modules.jobs.schemas import NormalizedJob


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    """The provider identity a run writes under.

    Persistence needs a display name and base URL to register a source the
    first time it is seen, and a normalized job carries neither.
    """

    key: str
    display_name: str
    base_url: str


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    """What happened to one record.

    A record that could not be written safely is reported as skipped with a
    failure attached, so a run never counts it as stored.
    """

    outcome: RecordOutcome
    job_id: UUID | None = None
    failure: RecordFailure | None = None


async def ensure_source(session: AsyncSession, source: SourceRegistration) -> JobSource:
    """Return the registered provider row, creating it the first time."""
    existing = (
        await session.scalars(select(JobSource).where(JobSource.key == source.key))
    ).one_or_none()
    if existing is not None:
        return existing

    created = JobSource(
        key=source.key,
        display_name=source.display_name,
        base_url=source.base_url,
    )
    session.add(created)
    await session.flush()
    return created


async def ensure_company(session: AsyncSession, display_name: str) -> Company:
    """Return a company matching the normalized name, creating it if absent.

    The normalized name is not unique, so the oldest match wins. Splitting two
    employers that normalize alike is a separate problem from ingestion, and
    guessing here would silently attach jobs to the wrong company.
    """
    normalized = normalize_company_name(display_name)
    statement = (
        select(Company)
        .where(Company.normalized_name == normalized)
        .order_by(Company.created_at, Company.id)
        .limit(1)
    )
    existing = (await session.scalars(statement)).one_or_none()
    if existing is not None:
        return existing

    created = Company(display_name=display_name)
    session.add(created)
    await session.flush()
    return created


def apply_fields(job: Job, incoming: NormalizedJob, fingerprint: str) -> None:
    """Copy every canonical field from an incoming job onto a stored one."""
    job.fingerprint = fingerprint
    job.title = incoming.title
    job.description = incoming.description
    job.location = incoming.location
    job.workplace_type = incoming.workplace_type
    job.employment_type = incoming.employment_type
    job.application_url = str(incoming.application_url)
    job.published_at = incoming.published_at
    job.expires_at = incoming.expires_at


async def persist_job(
    session: AsyncSession,
    incoming: NormalizedJob,
    *,
    source: SourceRegistration,
    seen_at: datetime,
) -> PersistenceResult:
    """Write one normalized job and its provenance, or report why not."""
    if source.key != incoming.provenance.source_key:
        return PersistenceResult(
            outcome=RecordOutcome.SKIPPED,
            failure=RecordFailure(
                stage=IngestionStage.PERSIST,
                reason=(
                    f"record belongs to source {incoming.provenance.source_key}, not {source.key}"
                ),
                source_job_id=incoming.provenance.source_job_id,
            ),
        )

    try:
        async with session.begin_nested():
            return await write(session, incoming, source=source, seen_at=seen_at)
    except SQLAlchemyError as error:
        return PersistenceResult(
            outcome=RecordOutcome.SKIPPED,
            failure=RecordFailure(
                stage=IngestionStage.PERSIST,
                reason=f"{type(error).__name__} while writing the record",
                source_job_id=incoming.provenance.source_job_id,
            ),
        )


async def write(
    session: AsyncSession,
    incoming: NormalizedJob,
    *,
    source: SourceRegistration,
    seen_at: datetime,
) -> PersistenceResult:
    """Apply one decision inside the caller's savepoint."""
    decision = await decide(session, incoming)

    if decision.outcome is DeduplicationOutcome.AMBIGUOUS:
        return PersistenceResult(
            outcome=RecordOutcome.SKIPPED,
            failure=RecordFailure(
                stage=IngestionStage.PERSIST,
                reason=(
                    f"fingerprint matches {len(decision.candidate_job_ids)} stored jobs; "
                    "resolve them before ingesting this record"
                ),
                source_job_id=incoming.provenance.source_job_id,
            ),
        )

    registered = await ensure_source(session, source)

    if decision.outcome is DeduplicationOutcome.NEW:
        job = Job(company=await ensure_company(session, incoming.company.display_name))
        apply_fields(job, incoming, decision.fingerprint)
        session.add(job)
        await session.flush()
        outcome = RecordOutcome.CREATED
    else:
        job = (await session.scalars(select(Job).where(Job.id == decision.job_id))).one()
        if decision.outcome is DeduplicationOutcome.CHANGED:
            apply_fields(job, incoming, decision.fingerprint)
            outcome = RecordOutcome.UPDATED
        else:
            outcome = RecordOutcome.SKIPPED

    await observe_job_provenance(
        session,
        job_id=job.id,
        source_id=registered.id,
        source_job_id=incoming.provenance.source_job_id,
        source_url=str(incoming.provenance.source_url),
        seen_at=seen_at,
        raw_payload=incoming.provenance.raw_payload,
    )
    await session.flush()
    return PersistenceResult(outcome=outcome, job_id=job.id)
