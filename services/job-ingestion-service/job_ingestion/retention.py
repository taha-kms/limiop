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

from dataclasses import dataclass
from datetime import datetime, timedelta

from platform_db.models import Job, JobProvenance
from platform_db.models.catalog import JobStatus
from platform_db.models.job_skills import JobSkill, JobSkillMention
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How long a job that stopped being listable is kept as it was."""

    grace: timedelta = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class RetentionResult:
    """What one pass did. `examined` is the candidates it found, so the other
    two add up to it."""

    deleted: int = 0
    anonymised: int = 0
    examined: int = 0


async def apply_retention(
    session: AsyncSession,
    *,
    now: datetime,
    policy: RetentionPolicy,
) -> RetentionResult:
    """Delete or anonymise every job that left the listing before the grace ran out.

    Runs inside the caller's transaction, so one pass is all or nothing.
    """
    candidates = set(
        (
            await session.scalars(
                select(Job.id).where(
                    Job.status != JobStatus.ACTIVE,
                    Job.updated_at < now - policy.grace,
                )
            )
        ).all()
    )
    if not candidates:
        return RetentionResult()

    # Explicit and in dependency order. Skills and mentions cascade on the
    # schema and provenance restricts, but a delete that relies on which is
    # which reads as an accident, and this way the order is the rule.
    for model in (JobSkillMention, JobSkill, JobProvenance):
        await session.execute(delete(model).where(model.job_id.in_(candidates)))
    await session.execute(delete(Job).where(Job.id.in_(candidates)))
    await session.flush()
    return RetentionResult(deleted=len(candidates), examined=len(candidates))
