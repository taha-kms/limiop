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
history keeps its shape without the content.

The "left the listing" moment is `jobs.updated_at`. The model declares
`onupdate=func.now()` and both status flips in `reconciliation` go through the
ORM, so the column moves exactly when a job stops being active. It also moves
whenever a source still writes the job, which only delays retention: a job a
source keeps sending has not left any listing yet. Provenance `retired_at` was
the alternative, and it says nothing about an expired job whose source still
carries it.

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
from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.config import Settings, get_settings
from job_ingestion.database import Database

logger = logging.getLogger(__name__)

# Which of the candidate jobs some user-facing row still points at. Nothing in
# the schema does yet; the tables that will (matches, saved jobs, applications)
# register a probe here rather than teaching this module their shape.
type ReferenceProbe = Callable[[AsyncSession, Collection[UUID]], Awaitable[set[UUID]]]

# Left in every provenance row of an anonymised job, in place of the payload.
# It is the marker that keeps the job from being a candidate again.
ANONYMISED_AT_KEY = "_anonymised_at"
ANONYMISED_DESCRIPTION = "Posting no longer available"


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How long a job that stopped being listable is kept as it was, and what
    counts as still needing it afterwards."""

    grace: timedelta = timedelta(days=30)
    references: tuple[ReferenceProbe, ...] = ()


@dataclass(frozen=True, slots=True)
class RetentionResult:
    """What one pass did. `examined` is the candidates it found, so the other
    two add up to it."""

    deleted: int = 0
    anonymised: int = 0
    examined: int = 0


DEFAULT_POLICY = RetentionPolicy()


async def run_retention(
    settings: Settings | None = None,
    policy: RetentionPolicy = DEFAULT_POLICY,
) -> RetentionResult:
    """Run one retention pass against the configured database and commit it."""
    app_settings = settings if settings is not None else get_settings()
    database = Database(app_settings.database_url)
    try:
        async with database.session() as session:
            result = await apply_retention(session, now=datetime.now(UTC), policy=policy)
            await session.commit()
        logger.info("applied catalogue retention: %s", result)
        return result
    finally:
        await database.dispose()


async def apply_retention(
    session: AsyncSession,
    *,
    now: datetime,
    policy: RetentionPolicy,
) -> RetentionResult:
    """Delete or anonymise every job that left the listing before the grace ran out.

    Runs inside the caller's transaction, so one pass is all or nothing.
    """
    already_anonymised = exists().where(
        JobProvenance.job_id == Job.id,
        JobProvenance.raw_payload.has_key(ANONYMISED_AT_KEY),
    )
    candidates = set(
        (
            await session.scalars(
                select(Job.id).where(
                    Job.status != JobStatus.ACTIVE,
                    Job.updated_at < now - policy.grace,
                    ~already_anonymised,
                )
            )
        ).all()
    )
    if not candidates:
        return RetentionResult()

    referenced: set[UUID] = set()
    for probe in policy.references:
        referenced |= await probe(session, candidates)

    await anonymise(session, referenced, at=now)
    await purge(session, candidates - referenced)
    await session.flush()
    return RetentionResult(
        deleted=len(candidates - referenced),
        anonymised=len(referenced),
        examined=len(candidates),
    )


async def anonymise(session: AsyncSession, job_ids: set[UUID], *, at: datetime) -> None:
    """Strip what the jobs said while leaving the rows other data points at.

    The company link stays because the schema requires one. The application URL
    is emptied rather than nulled for the same reason. Status is left alone: an
    anonymised job is still the withdrawn or expired job it was.
    """
    if not job_ids:
        return
    await session.execute(
        update(JobProvenance)
        .where(JobProvenance.job_id.in_(job_ids))
        .values(raw_payload={ANONYMISED_AT_KEY: at.isoformat()})
    )
    await session.execute(
        update(Job)
        .where(Job.id.in_(job_ids))
        .values(description=ANONYMISED_DESCRIPTION, location=None, application_url="")
    )


async def purge(session: AsyncSession, job_ids: set[UUID]) -> None:
    """Delete the jobs and everything that hangs off them.

    Explicit and in dependency order. Skills and mentions cascade on the schema
    and provenance restricts, but a delete that relies on which is which reads
    as an accident, and this way the order is the rule.
    """
    if not job_ids:
        return
    for model in (JobSkillMention, JobSkill, JobProvenance):
        await session.execute(delete(model).where(model.job_id.in_(job_ids)))
    await session.execute(delete(Job).where(Job.id.in_(job_ids)))
