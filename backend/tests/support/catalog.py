"""Shared job-catalog fixtures for tests that need real rows.

The query service and the HTTP surface both need a populated catalog, and both
need it emptied afterwards. Defining the seeding once keeps the two from
drifting into testing subtly different catalogs.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete

from app.db.session import Database
from app.modules.jobs.domain import EmploymentType, JobStatus, WorkplaceType
from app.modules.jobs.models import Company, Job, JobProvenance, JobSource

EPOCH = datetime(2026, 8, 1, 12, tzinfo=UTC)


def at(days: int) -> datetime:
    """A publication time, offset from a fixed point so tests never use the clock."""
    return EPOCH + timedelta(days=days)


async def clear(database: Database) -> None:
    """Empty the catalog in foreign-key order."""
    async with database.session() as session:
        await session.execute(delete(JobProvenance))
        await session.execute(delete(Job))
        await session.execute(delete(Company))
        await session.execute(delete(JobSource))
        await session.commit()


async def seed(database: Database, *specs: dict[str, Any]) -> dict[str, UUID]:
    """Insert one job per spec and return their ids by title.

    Companies are reused across specs naming the same employer, so a test can
    exercise the company filter without assembling the rows itself.
    """
    companies: dict[str, Company] = {}
    identifiers: dict[str, UUID] = {}

    async with database.session() as session:
        for spec in specs:
            name = str(spec.get("company", "Acme GmbH"))
            company = companies.get(name)
            if company is None:
                company = Company(display_name=name)
                companies[name] = company
            title = str(spec["title"])
            job = Job(
                company=company,
                fingerprint=f"v1:{uuid4().hex}",
                title=title,
                description=str(spec.get("description", "Work.")),
                location=spec.get("location"),
                workplace_type=spec.get("workplace_type", WorkplaceType.UNSPECIFIED),
                employment_type=spec.get("employment_type", EmploymentType.UNSPECIFIED),
                application_url=str(spec.get("application_url", "https://acme.example.com/apply")),
                published_at=spec.get("published_at"),
                status=spec.get("status", JobStatus.ACTIVE),
            )
            session.add(job)
            await session.flush()
            identifiers[title] = job.id
        await session.commit()

    return identifiers


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
