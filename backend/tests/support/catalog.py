"""Shared job-catalog fixtures for tests that need real rows.

The query service and the HTTP surface both need a populated catalog, and both
need it emptied afterwards. Defining the seeding once keeps the two from
drifting into testing subtly different catalogs.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from platform_db.models import Company, Job, JobProvenance, JobSource
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Database
from app.modules.jobs.domain import EmploymentType, JobStatus, WorkplaceType

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


def source_for(
    sources: dict[str, JobSource],
    session: AsyncSession,
    attribution: dict[str, Any],
) -> JobSource:
    """Register a board once per seeding call, however many jobs name it."""
    key = str(attribution["key"])
    source = sources.get(key)
    if source is None:
        source = JobSource(
            key=key,
            display_name=str(attribution.get("display_name", key.title())),
            base_url=str(attribution.get("base_url", f"https://{key}.example.com/api")),
        )
        session.add(source)
        sources[key] = source
    return source


async def seed(database: Database, *specs: dict[str, Any]) -> dict[str, UUID]:
    """Insert one job per spec and return their ids by title.

    Companies are reused across specs naming the same employer, so a test can
    exercise the company filter without assembling the rows itself.
    """
    companies: dict[str, Company] = {}
    sources: dict[str, JobSource] = {}
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
                match_key=f"v1:{uuid4().hex}",
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
            for attribution in spec.get("sources", ()):
                session.add(
                    JobProvenance(
                        job=job,
                        source=source_for(sources, session, attribution),
                        source_job_id=str(attribution.get("source_job_id", uuid4().hex)),
                        source_url=str(attribution["source_url"]),
                        first_seen_at=spec.get("published_at") or EPOCH,
                        last_seen_at=spec.get("published_at") or EPOCH,
                        raw_payload=attribution.get("raw_payload"),
                    )
                )
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
