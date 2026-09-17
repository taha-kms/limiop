"""What leaves the catalogue once it stopped being listable.

Reconciliation marks a job `removed` and expiry marks it `expired`, and nothing
serves either, but nothing deleted either. Retired provenance rows, their raw
payloads and withdrawn jobs would accumulate for as long as the service runs,
and two licences forbid exactly that: Adzuna's termination clause wants
acquired data removed, and France Travail keeps removed offers only anonymised.

The rule is one pass over the catalogue. A job that has not been `active` for
longer than the policy's grace period is a candidate. A candidate nothing
user-facing references is deleted with its provenance, skills and mentions. A
candidate that user-facing rows still reference is anonymised instead, so the
history keeps its shape without the content, and `jobs.anonymised_at` records
that it happened so the job is never a candidate again. Nothing here clears
that column: a source re-listing an anonymised job is issue #392.

The pass runs in pages, because a first run against a catalogue that has been
reconciling for months has more candidates than one statement can name. Each
page is selected under a row lock that skips rows another transaction holds,
acted on, and committed on its own, so an ingestion run writing a job at the
same moment either finds the row locked and waits, or has locked it first and
is left alone. Pages advance by key, oldest first, so one pass visits a row at
most once whatever it did to it. The statements that finally act restate the
whole predicate rather than trusting the page they were handed.

The "left the listing" moment is `jobs.updated_at`. The model declares
`onupdate=func.now()` and both status flips in `reconciliation` go through the
ORM, so the column moves exactly when a job stops being active. Provenance
`retired_at` was the alternative, and it says nothing about an expired job
whose source still carries it.

Per-source hooks are not here yet. France Travail's anonymise-at-retirement and
Adzuna's remove-when-disabled both attach to this policy when they land.
"""

import logging
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from platform_db.models import Job, JobProvenance
from platform_db.models.catalog import JobStatus
from platform_db.models.job_skills import JobSkill, JobSkillMention
from sqlalchemy import ColumnElement, delete, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.config import Settings, get_settings
from job_ingestion.database import Database

logger = logging.getLogger(__name__)

# Which of the candidate jobs some user-facing row still points at. Nothing in
# the schema does yet; the tables that will (matches, saved jobs, applications)
# register a probe here rather than teaching this module their shape. A probe
# is handed one page at a time, never more ids than the policy's batch size.
type ReferenceProbe = Callable[[AsyncSession, Collection[UUID]], Awaitable[set[UUID]]]

# What replaces every provenance payload of an anonymised job: the same
# instant `jobs.anonymised_at` records, so a payload read on its own still
# says why it is empty.
ANONYMISED_AT_KEY = "_anonymised_at"
ANONYMISED_DESCRIPTION = "Posting no longer available"

# Where a page ends: the (updated_at, id) of its last row.
type PageKey = tuple[datetime, UUID]


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How long a job that stopped being listable is kept as it was, what
    counts as still needing it afterwards, and how much one page takes on."""

    grace: timedelta = timedelta(days=30)
    references: tuple[ReferenceProbe, ...] = ()
    batch_size: int = 500

    def __post_init__(self) -> None:
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")


@dataclass(frozen=True, slots=True)
class RetentionResult:
    """What one pass did.

    `examined` counts the candidates the pass selected. A job the final
    re-check spared is examined but neither deleted nor anonymised, so the
    other two add up to it only when nothing moved under the pass.
    """

    deleted: int = 0
    anonymised: int = 0
    examined: int = 0


DEFAULT_POLICY = RetentionPolicy()


async def run_retention(
    settings: Settings | None = None,
    policy: RetentionPolicy = DEFAULT_POLICY,
) -> RetentionResult:
    """Run one retention pass against the configured database."""
    app_settings = settings if settings is not None else get_settings()
    database = Database(app_settings.database_url)
    try:
        async with database.session() as session:
            result = await apply_retention(session, now=datetime.now(UTC), policy=policy)
        logger.info("applied catalogue retention: %s", result)
        return result
    finally:
        await database.dispose()


def eligible(cutoff: datetime) -> tuple[ColumnElement[bool], ...]:
    """The candidate predicate, shared by the selection and by every statement
    that acts, so the two can never drift apart."""
    return (
        Job.status != JobStatus.ACTIVE,
        Job.updated_at < cutoff,
        Job.anonymised_at.is_(None),
    )


async def apply_retention(
    session: AsyncSession,
    *,
    now: datetime,
    policy: RetentionPolicy,
) -> RetentionResult:
    """Delete or anonymise every job that left the listing before the grace ran out.

    Commits the session after every page, so a pass that fails midway keeps
    what it finished and the next pass resumes where it stopped.
    """
    cutoff = now - policy.grace
    result = RetentionResult()
    after: PageKey | None = None
    while True:
        page, after = await select_page(session, cutoff=cutoff, size=policy.batch_size, after=after)
        if not page:
            return result

        referenced: set[UUID] = set()
        for probe in policy.references:
            referenced |= await probe(session, page) & page

        anonymised = await anonymise(session, referenced, cutoff=cutoff, at=now)
        deleted = await purge(session, page - referenced, cutoff=cutoff)
        await session.commit()
        result = RetentionResult(
            deleted=result.deleted + deleted,
            anonymised=result.anonymised + anonymised,
            examined=result.examined + len(page),
        )


async def select_page(
    session: AsyncSession,
    *,
    cutoff: datetime,
    size: int,
    after: PageKey | None,
) -> tuple[set[UUID], PageKey | None]:
    """The next candidates past `after`, locked until the page commits.

    Oldest first, so a backlog drains from the far end. Rows another
    transaction holds are skipped rather than waited for: that transaction is
    an ingestion run writing the job, and what it writes decides whether the
    job is still a candidate next time. Returns where the page ended, so the
    next one starts past it whatever this one did to its rows.
    """
    statement = (
        select(Job.id, Job.updated_at)
        .where(*eligible(cutoff))
        .order_by(Job.updated_at, Job.id)
        .limit(size)
        .with_for_update(skip_locked=True)
    )
    if after is not None:
        statement = statement.where(tuple_(Job.updated_at, Job.id) > after)
    rows = (await session.execute(statement)).all()
    if not rows:
        return set(), after
    last_id, last_updated_at = rows[-1]
    return {job_id for job_id, _ in rows}, (last_updated_at, last_id)


async def anonymise(
    session: AsyncSession,
    job_ids: set[UUID],
    *,
    cutoff: datetime,
    at: datetime,
) -> int:
    """Strip what the jobs said while leaving the rows other data points at.

    The company link stays because the schema requires one. The application URL
    is emptied rather than nulled for the same reason. Status is left alone: an
    anonymised job is still the withdrawn or expired job it was.
    """
    if not job_ids:
        return 0
    confirmed = set(
        (
            await session.scalars(
                update(Job)
                .where(Job.id.in_(job_ids), *eligible(cutoff))
                .values(
                    description=ANONYMISED_DESCRIPTION,
                    location=None,
                    application_url="",
                    anonymised_at=at,
                )
                .returning(Job.id)
            )
        ).all()
    )
    if confirmed:
        await session.execute(
            update(JobProvenance)
            .where(JobProvenance.job_id.in_(confirmed))
            .values(raw_payload={ANONYMISED_AT_KEY: at.isoformat()})
        )
    return len(confirmed)


async def purge(session: AsyncSession, job_ids: set[UUID], *, cutoff: datetime) -> int:
    """Delete the jobs and everything that hangs off them.

    Explicit and in dependency order. Skills and mentions cascade on the schema
    and provenance restricts, but a delete that relies on which is which reads
    as an accident, and this way the order is the rule.
    """
    if not job_ids:
        return 0
    confirmed = set(
        (await session.scalars(select(Job.id).where(Job.id.in_(job_ids), *eligible(cutoff)))).all()
    )
    if not confirmed:
        return 0
    for model in (JobSkillMention, JobSkill, JobProvenance):
        await session.execute(delete(model).where(model.job_id.in_(confirmed)))
    deleted = await session.scalars(
        delete(Job).where(Job.id.in_(confirmed), *eligible(cutoff)).returning(Job.id)
    )
    return len(deleted.all())
