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

from platform_db.models import Company, Job, JobProvenance, JobSource
from platform_db.models.catalog import (
    EmploymentType,
    JobStatus,
    WorkplaceType,
    normalize_company_name,
)
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from job_ingestion.contracts import IngestionStage, RecordFailure, RecordOutcome
from job_ingestion.deduplication import DeduplicationOutcome, decide
from job_ingestion.matching import match_key_of
from job_ingestion.schemas import NormalizedJob


async def observe_job_provenance(
    session: AsyncSession,
    *,
    job_id: UUID,
    source_id: UUID,
    source_job_id: str,
    source_url: str,
    seen_at: datetime,
    raw_payload: dict[str, object] | None = None,
) -> JobProvenance:
    """Insert or refresh one external record without owning the transaction."""
    if seen_at.tzinfo is None or seen_at.utcoffset() is None:
        raise ValueError("seen_at must be timezone-aware")

    insert_statement = insert(JobProvenance).values(
        job_id=job_id,
        source_id=source_id,
        source_job_id=source_job_id,
        source_url=source_url,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        raw_payload=raw_payload,
    )
    excluded = insert_statement.excluded
    statement = insert_statement.on_conflict_do_update(
        constraint="uq_job_provenance_source_id_source_job_id",
        set_={
            "source_url": excluded.source_url,
            "first_seen_at": func.least(
                JobProvenance.first_seen_at,
                excluded.first_seen_at,
            ),
            "last_seen_at": func.greatest(
                JobProvenance.last_seen_at,
                excluded.last_seen_at,
            ),
            "raw_payload": func.coalesce(
                excluded.raw_payload,
                JobProvenance.raw_payload,
            ),
            "retired_at": None,
        },
    ).returning(JobProvenance)

    return (await session.scalars(statement)).one()


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    """The provider identity a run writes under.

    Persistence needs a display name and base URL to register a source the
    first time it is seen, and a normalized job carries neither.
    """

    key: str
    display_name: str
    base_url: str
    # Higher wins when two sources describe the same field differently. An
    # employer's own board knows more about its posting than an aggregator that
    # copied it, so aggregators rank below the boards they copy from.
    precedence: int = 0


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
        # Refreshed rather than left alone: a source's identity and its ranking
        # are policy, and a policy change has to reach records written after it.
        existing.display_name = source.display_name
        existing.base_url = source.base_url
        existing.precedence = source.precedence
        return existing

    created = JobSource(
        key=source.key,
        display_name=source.display_name,
        base_url=source.base_url,
        precedence=source.precedence,
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


# A field a provider left empty, or filled with the fallback its vocabulary
# uses for "no idea", is not an account of that field. It is silence.
UNSTATED: tuple[object, ...] = (None, WorkplaceType.UNSPECIFIED, EmploymentType.UNSPECIFIED)


def is_stated(value: object) -> bool:
    """Whether a source actually said something about a field."""
    return value not in UNSTATED


def resolve(stored: object, incoming: object, *, incoming_outranks: bool) -> object:
    """Pick the value that survives when two sources describe one field.

    Silence never wins. A source that says nothing about a field cannot erase
    what another source said, whatever their ranking, because nothing
    distinguishes a provider that dropped a field from one that never carried
    it. Ninety percent of Arbeitnow postings state no workplace arrangement,
    so the alternative would be a catalogue that empties itself every run.

    When both sources speak, rank decides, and an equal rank goes to the
    incoming record so a single source can still correct itself.
    """
    if not is_stated(incoming):
        return stored
    if not is_stated(stored):
        return incoming
    return incoming if incoming_outranks else stored


def merge_fields(job: Job, incoming: NormalizedJob, *, incoming_outranks: bool) -> None:
    """Fold an incoming record into a stored job under the ownership rule.

    The match key is recomputed from what the merge produced rather than from
    what arrived. A job several sources contributed to holds values no single
    record matches, and a key describing the incoming record would describe a
    job that is not stored.
    """
    keep = job.id is not None

    def pick(stored: object, arriving: object) -> object:
        if not keep:
            return arriving
        return resolve(stored, arriving, incoming_outranks=incoming_outranks)

    job.title = str(pick(job.title, incoming.title))
    job.description = str(pick(job.description, incoming.description))
    location = pick(job.location, incoming.location)
    job.location = None if location is None else str(location)
    job.workplace_type = pick(job.workplace_type, incoming.workplace_type)  # type: ignore[assignment]
    job.employment_type = pick(job.employment_type, incoming.employment_type)  # type: ignore[assignment]
    job.application_url = str(pick(job.application_url, str(incoming.application_url)))
    job.published_at = pick(job.published_at, incoming.published_at)  # type: ignore[assignment]
    job.expires_at = pick(job.expires_at, incoming.expires_at)  # type: ignore[assignment]

    job.match_key = match_key_of(job.company.display_name, job.title)


def canonical_values(job: Job) -> tuple[object, ...]:
    """Everything the merge may change, for telling a real update from a no-op."""
    return (
        job.title,
        job.description,
        job.location,
        job.workplace_type,
        job.employment_type,
        job.application_url,
        job.published_at,
        job.expires_at,
        job.match_key,
    )


async def owner_precedence(session: AsyncSession, job_id: UUID) -> int | None:
    """The highest rank among sources that have already seen this job.

    Derived from provenance rather than stored on the job. The rows are already
    there, one per source per job, so a separate owner column would be a second
    copy of the same fact and a chance for the two to disagree.
    """
    statement = (
        select(func.max(JobSource.precedence))
        .select_from(JobProvenance)
        .join(JobSource, JobProvenance.source_id == JobSource.id)
        .where(JobProvenance.job_id == job_id)
    )
    highest: int | None = await session.scalar(statement)
    return highest


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
                    f"this record is indistinguishable from {len(decision.candidate_job_ids)} "
                    "stored jobs; "
                    "resolve them before ingesting this record"
                ),
                source_job_id=incoming.provenance.source_job_id,
            ),
        )

    registered = await ensure_source(session, source)

    if decision.outcome is DeduplicationOutcome.NEW:
        job = Job(company=await ensure_company(session, incoming.company.display_name))
        merge_fields(job, incoming, incoming_outranks=True)
        session.add(job)
        await session.flush()
        outcome = RecordOutcome.CREATED
    else:
        # The company is loaded with the job because the merge recomputes the
        # match key from it, and a lazy load there would run outside the
        # async context and fail.
        statement = select(Job).options(selectinload(Job.company)).where(Job.id == decision.job_id)
        job = (await session.scalars(statement)).one()
        if decision.outcome is DeduplicationOutcome.CHANGED:
            # An equal rank goes to the incoming record, so one source
            # correcting itself still lands.
            owner = await owner_precedence(session, job.id)
            before = canonical_values(job)
            merge_fields(
                job,
                incoming,
                incoming_outranks=owner is None or registered.precedence >= owner,
            )
            # A record can differ from what is stored and still change nothing,
            # because the merge may decline every field it disagrees about. That
            # is a skip, not an update, or a lower-ranked source would report
            # work it did not do on every run.
            outcome = (
                RecordOutcome.UPDATED if canonical_values(job) != before else RecordOutcome.SKIPPED
            )
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
    # A source listing it again contradicts the conclusion that nobody did.
    # Expiry is left alone: a stated date does not stop having passed because
    # the posting is still on a board.
    if job.status is JobStatus.REMOVED:
        job.status = JobStatus.ACTIVE
    await session.flush()
    return PersistenceResult(outcome=outcome, job_id=job.id)
