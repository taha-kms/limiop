"""Catalog cleanup around tests that write real rows, and one reading of it."""

from collections.abc import Awaitable, Callable
from datetime import datetime

from platform_db.models import Company, Job, JobBoard, JobProvenance, JobSource
from sqlalchemy import delete, select

from job_ingestion.database import Database


async def clear(database: Database) -> None:
    """Empty the catalog in foreign-key order."""
    async with database.session() as session:
        await session.execute(delete(JobProvenance))
        await session.execute(delete(Job))
        await session.execute(delete(JobBoard))
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


async def retired_at_by_source_job_id(database: Database) -> dict[str, datetime | None]:
    """When each provenance record was retired, or None while still listed."""
    async with database.session() as session:
        return {
            record.source_job_id: record.retired_at
            for record in (await session.scalars(select(JobProvenance))).all()
        }
