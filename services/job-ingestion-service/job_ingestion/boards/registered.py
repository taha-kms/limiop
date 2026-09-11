"""What one provider's run polls, read from the registry.

Ingestion no longer decides which boards to read. The registry does, and this
module is the one query that turns its rows into the slugs a run fetches.
"""

from platform_db.models import JobSource
from platform_db.models.boards import POLLED_STATUSES, BoardStatus, JobBoard
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def polled_slugs(session: AsyncSession, source_key: str) -> tuple[str, ...]:
    """Slugs a run polls for one provider: confirmed, named, or pinned rows, never blocked.

    A provider with no source row yet has no boards, which is what a fresh
    deployment looks like before discovery has run.
    """
    statement = (
        select(JobBoard.slug)
        .join(JobSource, JobBoard.source_id == JobSource.id)
        .where(
            JobSource.key == source_key,
            JobBoard.status != BoardStatus.BLOCKED,
            JobBoard.status.in_(POLLED_STATUSES) | JobBoard.pinned,
        )
        .order_by(JobBoard.slug)
    )
    return tuple((await session.scalars(statement)).all())
