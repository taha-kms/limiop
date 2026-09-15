"""Recording what one ingestion execution did.

Scheduler logs are ephemeral, so "did last night's Greenhouse run finish" has
to be answerable from a row rather than from whatever the task output still
holds. The row's own identifier is the run's correlation identifier.

Recording never fails a run. A pipeline that stopped because its bookkeeping
could not be written would be a worse outcome than bookkeeping nobody wrote.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from platform_db.models import IngestionRun, IngestionRunState
from sqlalchemy import Executable, insert, update

from job_ingestion.contracts import IngestionStage, IngestionSummary, RecordFailure
from job_ingestion.database import Database
from job_ingestion.reconciliation import reconcile

if TYPE_CHECKING:
    from job_ingestion.credentials import Unconfigured

logger = logging.getLogger(__name__)

# Enough to see the shape of a bad run without turning the column into a log.
SAMPLED_REASONS = 5


def failure_summary(failures: Sequence[RecordFailure]) -> dict[str, object] | None:
    """Counts per stage, and a bounded sample of reasons.

    Never a traceback and never a provider payload. Reasons here are already
    written by this service — a stage rejection's message, or the name of a
    database error class — so nothing arrives that would need redacting before
    a person could read it.
    """
    if not failures:
        return None
    by_stage: dict[str, int] = {}
    for failure in failures:
        by_stage[failure.stage.value] = by_stage.get(failure.stage.value, 0) + 1
    return {
        "total": len(failures),
        "by_stage": by_stage,
        "reasons": sorted({failure.reason for failure in failures})[:SAMPLED_REASONS],
    }


@asynccontextmanager
async def recorded_run(database: Database, source_key: str) -> AsyncIterator[UUID]:
    """Open a run row, and close it however the run ends.

    A run that raises is recorded as failed and the exception continues, so a
    caller still sees what happened. A run that returns without a summary is
    still terminal: `complete_run` is what marks it, and leaving without either
    means the process died, which the row's `running` state then says.
    """
    run_id = uuid4()
    started_at = datetime.now(UTC)
    await _write(
        database,
        insert(IngestionRun).values(
            id=run_id,
            source_key=source_key,
            state=IngestionRunState.RUNNING,
            started_at=started_at,
            fetched=0,
            created=0,
            updated=0,
            skipped=0,
            failed=0,
            reached_the_end=False,
            stopped_at_budget=False,
            mentions_resolved=0,
            mentions_unknown=0,
            extraction_failed=0,
        ),
    )
    try:
        yield run_id
    except Exception as error:
        await _write(
            database,
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                state=IngestionRunState.FAILED,
                finished_at=datetime.now(UTC),
                # The class name, not the message: a provider's error text can
                # carry a URL with a key in it, and this column is read by
                # people rather than parsed by code.
                failure_summary={"total": 1, "by_stage": {}, "reasons": [type(error).__name__]},
            ),
        )
        raise


async def complete_run(database: Database, run_id: UUID, summary: IngestionSummary) -> None:
    """Mark a run terminal and record what it did.

    Completed, not failed, even with record failures in it. A run that handled
    a bad record and carried on did its job; the counts say how much of it was
    clean, and `source_exhausted` already refuses the conclusions a failure
    should deny.
    """
    await _write(
        database,
        update(IngestionRun)
        .where(IngestionRun.id == run_id)
        .values(
            state=IngestionRunState.COMPLETED,
            finished_at=datetime.now(UTC),
            fetched=summary.fetched,
            created=summary.created,
            updated=summary.updated,
            skipped=summary.skipped,
            failed=summary.failed,
            reached_the_end=summary.reached_the_end,
            stopped_at_budget=summary.stopped_at_budget,
            alias_version=summary.alias_version,
            mentions_resolved=summary.mentions_resolved,
            mentions_unknown=summary.mentions_unknown,
            extraction_failed=summary.extraction_failed,
            failure_summary=failure_summary(summary.failures),
        ),
    )


async def run_recorded_ingestion(
    database: Database,
    source_key: str,
    build: Callable[[Database], Awaitable[IngestionSummary]],
    *,
    started_at: datetime,
) -> IngestionSummary:
    """Record one ingestion run around a caller-supplied execution.

    `build` does whatever is provider-specific: opening a client, assembling
    the stages, executing them against `database`. Everything on either side
    of that is the same for every provider that writes to this catalogue --
    open the run row, reconcile against what this run saw, and mark the row
    terminal -- so it lives here once instead of being copied into every
    `ingest_*` entry point.

    The caller still owns `database` itself: constructing the engine and
    disposing of it happens around this call, not inside it, because how a
    provider's config resolves to a database URL is not this function's
    business.
    """
    async with recorded_run(database, source_key) as run_id:
        summary = await build(database)
        async with database.session() as session:
            await reconcile(session, summary, run_started_at=started_at)
            await session.commit()
    await complete_run(database, run_id, summary)
    return summary


async def record_unconfigured_run(
    database: Database,
    source_key: str,
    unconfigured: "Unconfigured",
    *,
    started_at: datetime,
) -> IngestionSummary:
    """Record a run for a source whose credentials are not all set.

    A deployment enables sources one at a time, so a missing credential is not
    a scheduler failure: the task still succeeds, and the run row it leaves
    behind says why nothing was fetched. `started_at` is accepted so a caller
    that captured it before resolving credentials -- the same moment it would
    hand to `run_recorded_ingestion` on the configured path -- can pass the
    same value on either branch; this function does not otherwise use it,
    since `recorded_run` stamps the row's own start time when it opens.

    Unlike `run_recorded_ingestion`, this never calls `reconcile`: a run that
    saw nothing must not be read as a run that saw the source and found it
    empty, and reconciliation exists to draw exactly that distinction.
    """
    async with recorded_run(database, source_key) as run_id:
        summary = IngestionSummary(
            source_key=source_key,
            failures=(RecordFailure(stage=IngestionStage.FETCH, reason=unconfigured.reason),),
        )
    await complete_run(database, run_id, summary)
    return summary


async def _write(database: Database, statement: Executable) -> None:
    """Run one bookkeeping statement, and never let it end the ingestion."""
    try:
        async with database.session() as session:
            await session.execute(statement)
            await session.commit()
    except Exception:
        logger.warning("an ingestion run could not be recorded", exc_info=True)
