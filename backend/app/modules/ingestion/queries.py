"""Reading what the ingestion pipelines have most recently done.

The runs table is written by a separate service on a schedule nobody watches.
Reading it is the only way the API can say whether the catalogue is still being
fed, so the statement lives here rather than in a handler.
"""

from platform_db.models.ingestion import IngestionRun
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession


def latest_run_per_source() -> Select[tuple[IngestionRun]]:
    """The most recent run of each source, whatever state it reached.

    `DISTINCT ON` rather than a correlated subquery: one index scan over
    `(source_key, started_at)` answers it, and the ordering the index already
    keeps is the ordering that picks the winner.

    A run still in flight is the most recent one and is reported as such. A
    source that has never run has no row and is therefore absent, which is the
    honest answer: reporting it as idle would claim something about a pipeline
    nothing here has ever seen.
    """
    return (
        select(IngestionRun)
        .distinct(IngestionRun.source_key)
        # The identifier breaks a tie between runs that started in the same
        # instant, so the same run is reported twice running rather than one
        # arbitrarily each time.
        .order_by(
            IngestionRun.source_key,
            IngestionRun.started_at.desc(),
            IngestionRun.id.desc(),
        )
    )


async def read_latest_runs(session: AsyncSession) -> tuple[IngestionRun, ...]:
    return tuple((await session.scalars(latest_run_per_source())).all())
