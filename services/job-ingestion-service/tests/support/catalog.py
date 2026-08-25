"""Catalog cleanup around tests that write real rows."""

from collections.abc import Awaitable, Callable

from platform_db.models import Company, Job, JobProvenance, JobSource
from sqlalchemy import delete

from job_ingestion.database import Database


async def clear(database: Database) -> None:
    """Empty the catalog in foreign-key order."""
    async with database.session() as session:
        await session.execute(delete(JobProvenance))
        await session.execute(delete(Job))
        await session.execute(delete(Company))
        await session.execute(delete(JobSource))
        await session.commit()


async def with_empty_catalog(
    database: Database,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    """Run one test against a catalog that starts and ends empty."""
    try:
        await clear(database)
        await test(database)
    finally:
        await clear(database)
