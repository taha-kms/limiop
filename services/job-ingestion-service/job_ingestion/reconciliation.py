"""Concluding that a posting is gone.

A posting disappears from a board rather than announcing that it closed. Every
source examined states an expiry date in its schema and leaves it empty in
practice, so absence between runs is the only signal there is.

Absence is weak evidence, and it is only evidence at all when the alternatives
are excluded. A run that stopped at its record budget, gave up on a board, or
failed on a single record has postings it did not see, and an unseen posting
looks exactly like one that is gone. So reconciliation refuses to run at all
unless the run exhausted its source, which `IngestionSummary.source_exhausted`
answers and nothing here second-guesses.

The conclusion is drawn in two steps, because one source is not the catalogue:

1. **Per source.** A provenance record the run did not see is retired. That is
   a fact about one board: this company stopped advertising this posting there.
2. **Per job.** A job is withdrawn only once no source still lists it. A job
   dropped by an aggregator but still on the employer's own board is still open,
   and saying otherwise would hide a real vacancy.

Reappearance runs backwards through the same two steps, so a posting that comes
back is the job it was rather than a new one.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from platform_db.models import Job, JobProvenance, JobSource
from platform_db.models.catalog import JobStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.contracts import IngestionSummary


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """What one reconciliation concluded.

    `ran` is false when the run was not entitled to conclude anything, which is
    reported rather than hidden: a lifecycle that quietly stops working is worse
    than one that says it did not run.
    """

    ran: bool
    reason: str | None = None
    provenance_retired: int = 0
    jobs_withdrawn: int = 0

    @property
    def skipped(self) -> bool:
        return not self.ran


def why_not(summary: IngestionSummary) -> str | None:
    """Why this run may not conclude a posting is gone, or nothing if it may."""
    if summary.stopped_at_budget:
        return "the run stopped at its record budget and did not see the rest"
    if not summary.reached_the_end:
        return "the run did not reach the end of the source"
    if summary.failures:
        return (
            f"the run had {len(summary.failures)} failure(s) and cannot account for every posting"
        )
    if not summary.processing_complete:
        return "the run did not finish processing what it fetched"
    return None


async def reconcile(
    session: AsyncSession,
    summary: IngestionSummary,
    *,
    run_started_at: datetime,
) -> ReconciliationResult:
    """Retire what this source stopped listing, and withdraw what nobody lists.

    `run_started_at` separates seen from unseen. Provenance is refreshed as each
    record is written, so anything this source still carries has a last-seen
    time at or after the moment the run began.
    """
    refusal = why_not(summary)
    if refusal is not None:
        return ReconciliationResult(ran=False, reason=refusal)

    source = (
        await session.scalars(select(JobSource).where(JobSource.key == summary.source_key))
    ).one_or_none()
    if source is None:
        # A source that has never written anything cannot have stopped listing
        # anything either.
        return ReconciliationResult(ran=True)

    unseen = (
        await session.scalars(
            select(JobProvenance).where(
                JobProvenance.source_id == source.id,
                JobProvenance.retired_at.is_(None),
                JobProvenance.last_seen_at < run_started_at,
            )
        )
    ).all()
    if not unseen:
        return ReconciliationResult(ran=True)

    for record in unseen:
        record.retired_at = run_started_at
    await session.flush()

    # Deduplicated because one source can hold several records for one job,
    # and the job only needs deciding once.
    withdrawn = await withdraw_jobs_nobody_lists(
        session,
        {record.job_id for record in unseen},
    )
    return ReconciliationResult(
        ran=True,
        provenance_retired=len(unseen),
        jobs_withdrawn=withdrawn,
    )


async def withdraw_jobs_nobody_lists(session: AsyncSession, job_ids: set[UUID]) -> int:
    """Mark a job removed only when no source still lists it.

    Counts the jobs this call changed, not the jobs that end up removed, so
    reconciling twice reports the second pass as the no-op it was.
    """
    withdrawn = 0
    for job_id in job_ids:
        still_listed = await session.scalar(
            select(JobProvenance.id)
            .where(JobProvenance.job_id == job_id, JobProvenance.retired_at.is_(None))
            .limit(1)
        )
        if still_listed is not None:
            continue
        job = await session.get(Job, job_id)
        # An identifier naming no job is nothing to withdraw. Reconciliation
        # takes these from provenance rows, so it cannot produce one, but the
        # function is callable on its own and says what it does with one.
        if job is None or job.status is JobStatus.REMOVED:
            continue
        job.status = JobStatus.REMOVED
        withdrawn += 1
    await session.flush()
    return withdrawn


async def expire_jobs_past_their_stated_date(session: AsyncSession, *, now: datetime) -> int:
    """Mark jobs expired once the date they themselves gave has passed.

    Independent of any run and of any source. This is a stated fact rather than
    an inference from absence, so it needs no exhausted run to license it, and
    a job with no stated date is never touched by it.
    """
    lapsed = (
        await session.scalars(
            select(Job).where(
                Job.expires_at.is_not(None),
                Job.expires_at < now,
                Job.status == JobStatus.ACTIVE,
            )
        )
    ).all()
    for job in lapsed:
        job.status = JobStatus.EXPIRED
    await session.flush()
    return len(lapsed)
