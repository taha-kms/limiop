"""Applying one deduplication decision to the database.

Each record is written inside a savepoint. A record that violates a constraint
rolls back only itself, so one bad posting cannot discard the batch it arrived
with, and a caller can keep using the same session afterwards.

The service writes; it does not decide. Whether a job is new, changed, or
already known comes from `deduplication.decide`.
"""

from collections.abc import Collection
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
from job_ingestion.deduplication import PARTIAL_DESCRIPTION_KEY, DeduplicationOutcome, decide
from job_ingestion.matching import match_key_of
from job_ingestion.schemas import NormalizedJob

# The key under which a provenance row records how many optional canonical
# fields its record stated, beside `PARTIAL_DESCRIPTION_KEY`. Ownership
# compares one source's record against another's, and the payload is the
# only place a row keeps what its own record said once the job has merged it.
STATED_FIELDS_KEY = "_stated_fields"


def stored_payload(incoming: NormalizedJob) -> dict[str, object]:
    """The payload a provenance row keeps, with what ownership needs folded in.

    A partial description and the stated-field count are recorded inside
    `raw_payload` rather than in columns of their own. The flag exists so that
    deduplication can refuse to text-match the record later, the count so
    that a rival can be judged against this record rather than against the
    merged job, and the payload is already the one place a row keeps what is
    known about the record it came from; columns would be a schema change
    for two facts that only ever travel with that payload. The provider's
    own keys are stored untouched, so nothing that was written before these
    keys existed reads any differently.

    Both keys are written every time, the flag as an explicit `False` when
    the record is not partial. The upsert keeps the old payload when the new
    one is null, so a record that truncated once and recovered with no
    payload of its own would otherwise keep reading as a snippet forever.
    """
    provenance = incoming.provenance
    return {
        **(provenance.raw_payload or {}),
        PARTIAL_DESCRIPTION_KEY: provenance.partial_description,
        STATED_FIELDS_KEY: stated_field_count(incoming),
    }


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


async def stored_posting_counts(
    session: AsyncSession,
    employers: Collection[str],
) -> dict[str, int]:
    """How many postings the catalogue already holds for each named employer.

    Keyed by normalized name, which is how employers are identified everywhere
    else. Counts rather than descriptions: what this answers is whether an
    employer has enough postings to have a template, and a count is the whole
    answer at a fraction of the reading.
    """
    if not employers:
        return {}
    rows = await session.execute(
        select(Company.normalized_name, func.count(Job.id))
        .join(Job, Job.company_id == Company.id)
        .where(Company.normalized_name.in_(set(employers)))
        .group_by(Company.normalized_name)
    )
    return {name: count for name, count in rows}


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


# The optional canonical fields, which is where two accounts of one posting
# differ in how much they say. The title, description and application URL are
# required by the contract, so every record states them and they separate
# nothing.
OPTIONAL_CANONICAL_FIELDS = (
    "location",
    "workplace_type",
    "employment_type",
    "published_at",
    "expires_at",
)


def stated_field_count(record: Job | NormalizedJob) -> int:
    """How many of the optional canonical fields a record actually states."""
    return sum(is_stated(getattr(record, name)) for name in OPTIONAL_CANONICAL_FIELDS)


@dataclass(frozen=True, slots=True)
class Owner:
    """The account the stored canonical fields currently belong to.

    Read off the job's live provenance rows from every source but the one
    now writing: the sources at the highest rank among them, taken together.
    `partial` is true only when each of them delivered a snippet, because a
    full description at that rank would have won the field from a snippet;
    `stated` is the most optional fields any of them stated, for the same
    reason.
    """

    precedence: int
    first_seen_at: datetime
    partial: bool
    stated: int


def payload_facts(payload: dict[str, object] | None) -> tuple[bool, int]:
    """What a provenance row's payload records about its own record.

    A row written before the keys existed reads as a full record that stated
    nothing, which is the most it can be trusted to have said.
    """
    facts = payload or {}
    stated = facts.get(STATED_FIELDS_KEY)
    return (
        facts.get(PARTIAL_DESCRIPTION_KEY) is True,
        stated if isinstance(stated, int) else 0,
    )


@dataclass(frozen=True, slots=True)
class Rivals:
    """What the other sources on a job have said, seen from the one writing.

    `owner` is read off the live rows only: a source that stopped listing the
    job no longer ranks. `supplied_full_text` counts retired rows too, since
    the full description a source once supplied is still the one the job
    holds after that source has gone.
    """

    owner: Owner | None
    supplied_full_text: bool


async def rivals_of(session: AsyncSession, job_id: UUID, *, other_than: UUID) -> Rivals:
    """Every other source's account of a job, summarised for the ownership rule.

    Derived from provenance rather than stored on the job. The rows are already
    there, one per source per job, so a separate owner column would be a second
    copy of the same fact and a chance for the two to disagree.
    """
    statement = (
        select(
            JobSource.precedence,
            JobProvenance.first_seen_at,
            JobProvenance.retired_at.is_(None),
            JobProvenance.raw_payload,
        )
        .select_from(JobProvenance)
        .join(JobSource, JobProvenance.source_id == JobSource.id)
        .where(JobProvenance.job_id == job_id, JobProvenance.source_id != other_than)
    )
    rows = [
        (precedence, seen, live, *payload_facts(payload))
        for precedence, seen, live, payload in (await session.execute(statement)).all()
    ]
    supplied_full_text = any(not partial for _rank, _seen, _live, partial, _stated in rows)
    ranked = [row for row in rows if row[2]]
    if not ranked:
        return Rivals(owner=None, supplied_full_text=supplied_full_text)
    highest = max(precedence for precedence, _seen, _live, _partial, _stated in ranked)
    owning = [row for row in ranked if row[0] == highest]
    owner = Owner(
        precedence=highest,
        first_seen_at=min(seen for _rank, seen, _live, _partial, _stated in owning),
        partial=all(partial for _rank, _seen, _live, partial, _stated in owning),
        stated=max(stated for _rank, _seen, _live, _partial, stated in owning),
    )
    return Rivals(owner=owner, supplied_full_text=supplied_full_text)


async def first_listed_at(
    session: AsyncSession, job_id: UUID, source_id: UUID, seen_at: datetime
) -> datetime:
    """When a source first listed a job, counting the record now arriving.

    The arriving record has no provenance row yet, and the row it will get
    keeps the least of its `first_seen_at` and `seen_at`, so this is that
    value ahead of the write. Every row the source holds for the job counts,
    retired or not: a listing the source dropped and brought back still dates
    from when it first appeared.
    """
    earliest: datetime | None = await session.scalar(
        select(func.min(JobProvenance.first_seen_at)).where(
            JobProvenance.job_id == job_id,
            JobProvenance.source_id == source_id,
        )
    )
    return seen_at if earliest is None else min(earliest, seen_at)


async def incoming_outranks(
    session: AsyncSession,
    job: Job,
    registered: JobSource,
    incoming: NormalizedJob,
    *,
    seen_at: datetime,
) -> bool:
    """Whether the arriving record takes the fields it contests from the owner.

    Rank decides first, as it always has: a higher-ranked source wins outright
    and a lower-ranked one loses outright. Between sources of equal rank the
    more complete record owns the canonical fields. Aggregators carry the same
    employer text as each other, so rank cannot tell them apart and how much
    of the posting a record accounts for is the only signal left. A full
    description outranks a snippet, and then the record stating more of
    `OPTIONAL_CANONICAL_FIELDS` wins. The comparison is against the owner's
    own record as its provenance row recorded it, never against the merged
    job: the job holds what every contributor said, so measured against it no
    single source could stay complete enough to change the text again.

    At equal completeness the source that listed the job first keeps it. Once
    both sources have been seen, that date is the same whichever of them ran
    last, so the record stops depending on the order of the runs. A source
    that listed the job before any rival still lands its own corrections; a
    source with no rival at its rank always does.
    """
    rivals = await rivals_of(session, job.id, other_than=registered.id)
    if incoming.provenance.partial_description and rivals.supplied_full_text:
        return False

    owner = rivals.owner
    if owner is None or registered.precedence != owner.precedence:
        return owner is None or registered.precedence > owner.precedence

    arriving = (not incoming.provenance.partial_description, stated_field_count(incoming))
    stored = (not owner.partial, owner.stated)
    if arriving != stored:
        return arriving > stored

    listed_at = await first_listed_at(session, job.id, registered.id, seen_at)
    return listed_at < owner.first_seen_at


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
            before = canonical_values(job)
            merge_fields(
                job,
                incoming,
                incoming_outranks=await incoming_outranks(
                    session, job, registered, incoming, seen_at=seen_at
                ),
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
        raw_payload=stored_payload(incoming),
    )
    # A source listing it again contradicts the conclusion that nobody did.
    # Expiry is left alone: a stated date does not stop having passed because
    # the posting is still on a board.
    if job.status is JobStatus.REMOVED:
        job.status = JobStatus.ACTIVE
    await session.flush()
    return PersistenceResult(outcome=outcome, job_id=job.id)
