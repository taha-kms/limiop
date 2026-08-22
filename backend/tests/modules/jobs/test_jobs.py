import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.db.base import Base
from app.db.session import Database
from app.modules.jobs.domain import EmploymentType, JobStatus, WorkplaceType
from app.modules.jobs.models import Company, Job


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                await session.execute(delete(Job))
                await session.execute(delete(Company))
                await session.commit()
            await test(database)
        finally:
            async with database.session() as session:
                await session.execute(delete(Job))
                await session.execute(delete(Company))
                await session.commit()
            await database.dispose()

    asyncio.run(run())


def test_job_uses_shared_metadata_and_canonical_columns() -> None:
    assert Job.metadata is Base.metadata
    assert set(Job.__table__.columns.keys()) == {
        "match_key",
        "id",
        "company_id",
        "title",
        "description",
        "location",
        "workplace_type",
        "employment_type",
        "application_url",
        "published_at",
        "expires_at",
        "status",
        "created_at",
        "updated_at",
    }


@pytest.mark.integration
def test_job_round_trip(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        company = Company(display_name="Acme GmbH")
        job = Job(
            company=company,
            title="Data Engineer",
            description="Build reliable data pipelines.",
            location="Berlin, Germany",
            workplace_type=WorkplaceType.HYBRID,
            employment_type=EmploymentType.FULL_TIME,
            application_url="https://example.com/jobs/data-engineer",
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
            expires_at=datetime(2026, 9, 1, tzinfo=UTC),
        )

        async with database.session() as session:
            session.add(job)
            await session.commit()
            job_id = job.id

        async with database.session() as session:
            stored = await session.scalar(
                select(Job).options(selectinload(Job.company)).where(Job.id == job_id)
            )

        assert stored is not None
        assert isinstance(stored.id, UUID)
        assert stored.company.display_name == "Acme GmbH"
        assert stored.title == "Data Engineer"
        assert stored.description == "Build reliable data pipelines."
        assert stored.location == "Berlin, Germany"
        assert stored.workplace_type is WorkplaceType.HYBRID
        assert stored.employment_type is EmploymentType.FULL_TIME
        assert stored.status is JobStatus.ACTIVE
        assert stored.application_url == "https://example.com/jobs/data-engineer"
        assert stored.published_at == datetime(2026, 8, 1, tzinfo=UTC)
        assert stored.expires_at == datetime(2026, 9, 1, tzinfo=UTC)
        assert stored.created_at.tzinfo is not None
        assert stored.updated_at.tzinfo is not None

    run_database_test(database_url, exercise)


INVALID_JOB_VALUES: list[dict[str, object]] = [
    {"workplace_type": "distributed"},
    {"employment_type": "freelance"},
    {"status": "unknown"},
    {"company_id": None},
    {"company_id": uuid4()},
    {
        "published_at": datetime(2026, 9, 1, tzinfo=UTC),
        "expires_at": datetime(2026, 8, 1, tzinfo=UTC),
    },
]


@pytest.mark.integration
@pytest.mark.parametrize("overrides", INVALID_JOB_VALUES)
def test_job_constraints_reject_invalid_records(
    database_url: PostgresDsn,
    overrides: dict[str, object],
) -> None:
    async def exercise(database: Database) -> None:
        company = Company(display_name="Acme GmbH")
        async with database.session() as session:
            session.add(company)
            await session.commit()

        parameters: dict[str, object] = {
            "id": uuid4(),
            "company_id": company.id,
            "title": "Data Engineer",
            "description": "Build reliable data pipelines.",
            "workplace_type": "remote",
            "employment_type": "full-time",
            "application_url": "https://example.com/jobs/data-engineer",
            "published_at": None,
            "expires_at": None,
            "status": "active",
        }
        parameters.update(overrides)

        with pytest.raises(IntegrityError):
            async with database.session() as session:
                await session.execute(
                    text(
                        """
                        INSERT INTO jobs (
                            id,
                            company_id,
                            title,
                            description,
                            workplace_type,
                            employment_type,
                            application_url,
                            published_at,
                            expires_at,
                            status
                        ) VALUES (
                            :id,
                            :company_id,
                            :title,
                            :description,
                            :workplace_type,
                            :employment_type,
                            :application_url,
                            :published_at,
                            :expires_at,
                            :status
                        )
                        """
                    ),
                    parameters,
                )
                await session.commit()

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_job_query_indexes_exist(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            index_names = set(
                await session.scalars(
                    text(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = current_schema()
                          AND tablename = 'jobs'
                        """
                    )
                )
            )

        assert {
            "ix_jobs_company_id",
            "ix_jobs_location",
            "ix_jobs_status_expires_at",
            "ix_jobs_status_published_at_id",
        } <= index_names

    run_database_test(database_url, exercise)
