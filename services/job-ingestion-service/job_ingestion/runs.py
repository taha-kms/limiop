"""Recording what one ingestion execution did.

Scheduler logs are ephemeral, so "did last night's Greenhouse run finish" has
to be answerable from a row rather than from whatever the task output still
holds. The row's own identifier is the run's correlation identifier.

Recording never fails a run. A pipeline that stopped because its bookkeeping
could not be written would be a worse outcome than bookkeeping nobody wrote.
"""

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from platform_db.models import IngestionRun, IngestionRunState
from sqlalchemy import Executable, insert, update

from job_ingestion.contracts import IngestionSummary, RecordFailure
from job_ingestion.database import Database

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


async def _write(database: Database, statement: Executable) -> None:
    """Run one bookkeeping statement, and never let it end the ingestion."""
    try:
        async with database.session() as session:
            await session.execute(statement)
            await session.commit()
    except Exception:
        logger.warning("an ingestion run could not be recorded", exc_info=True)
