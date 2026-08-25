import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from platform_db.base import Base
from platform_db.models import Company, Job, JobProvenance, JobSource
from pydantic import PostgresDsn
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.db.session import Database
from app.modules.jobs.repositories import observe_job_provenance


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                await session.execute(delete(JobProvenance))
                await session.execute(delete(Job))
                await session.execute(delete(Company))
                await session.execute(delete(JobSource))
                await session.commit()
            await test(database)
        finally:
            async with database.session() as session:
                await session.execute(delete(JobProvenance))
                await session.execute(delete(Job))
                await session.execute(delete(Company))
                await session.execute(delete(JobSource))
                await session.commit()
            await database.dispose()

    asyncio.run(run())


async def create_job_and_sources(
    database: Database,
    source_keys: Sequence[str],
) -> tuple[UUID, list[UUID]]:
    company = Company(display_name="Acme GmbH")
    job = Job(
        company=company,
        title="Data Engineer",
        description="Build reliable data pipelines.",
        application_url="https://example.com/jobs/data-engineer",
    )
    sources = [
        JobSource(
            key=key,
            display_name=key.title(),
            base_url=f"https://{key}.example.com",
        )
        for key in source_keys
    ]

    async with database.session() as session:
        session.add_all([job, *sources])
        await session.commit()

    return job.id, [source.id for source in sources]


def test_job_provenance_uses_shared_metadata() -> None:
    assert JobProvenance.metadata is Base.metadata


def test_job_provenance_repr_excludes_raw_payload() -> None:
    observed_at = datetime(2026, 8, 18, 10, tzinfo=UTC)
    provenance = JobProvenance(
        job_id=uuid4(),
        source_id=uuid4(),
        source_job_id="external-42",
        source_url="https://example.com/jobs/42",
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        raw_payload={"private-marker": "must-not-appear"},
    )

    assert "must-not-appear" not in repr(provenance)


@pytest.mark.integration
def test_one_job_accepts_multiple_source_records(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        job_id, source_ids = await create_job_and_sources(
            database,
            ["arbeitnow", "jobicy"],
        )
        observed_at = datetime(2026, 8, 18, 10, tzinfo=UTC)

        async with database.session() as session:
            session.add_all(
                [
                    JobProvenance(
                        job_id=job_id,
                        source_id=source_ids[0],
                        source_job_id="external-42",
                        source_url="https://arbeitnow.example.com/jobs/42",
                        first_seen_at=observed_at,
                        last_seen_at=observed_at,
                        raw_payload={"title": "Data Engineer"},
                    ),
                    JobProvenance(
                        job_id=job_id,
                        source_id=source_ids[1],
                        source_job_id="external-42",
                        source_url="https://jobicy.example.com/jobs/42",
                        first_seen_at=observed_at,
                        last_seen_at=observed_at,
                    ),
                ]
            )
            await session.commit()

        async with database.session() as session:
            stored = list(
                await session.scalars(select(JobProvenance).order_by(JobProvenance.source_url))
            )

        assert len(stored) == 2
        assert {record.job_id for record in stored} == {job_id}
        assert {record.source_id for record in stored} == set(source_ids)
        assert {record.source_job_id for record in stored} == {"external-42"}
        assert {record.raw_payload is None for record in stored} == {False, True}

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_source_record_identity_is_unique(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        job_id, [source_id] = await create_job_and_sources(database, ["arbeitnow"])
        observed_at = datetime(2026, 8, 18, 10, tzinfo=UTC)

        with pytest.raises(IntegrityError):
            async with database.session() as session:
                session.add_all(
                    [
                        JobProvenance(
                            job_id=job_id,
                            source_id=source_id,
                            source_job_id="external-42",
                            source_url="https://arbeitnow.example.com/jobs/42",
                            first_seen_at=observed_at,
                            last_seen_at=observed_at,
                        ),
                        JobProvenance(
                            job_id=job_id,
                            source_id=source_id,
                            source_job_id="external-42",
                            source_url="https://arbeitnow.example.com/jobs/duplicate",
                            first_seen_at=observed_at,
                            last_seen_at=observed_at,
                        ),
                    ]
                )
                await session.commit()

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_reseeing_source_record_updates_existing_provenance(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        job_id, [source_id] = await create_job_and_sources(database, ["arbeitnow"])
        first_seen_at = datetime(2026, 8, 18, 10, tzinfo=UTC)
        last_seen_at = datetime(2026, 8, 19, 10, tzinfo=UTC)

        async with database.session() as session:
            first = await observe_job_provenance(
                session,
                job_id=job_id,
                source_id=source_id,
                source_job_id="external-42",
                source_url="https://arbeitnow.example.com/jobs/42",
                seen_at=first_seen_at,
                raw_payload={"title": "Data Engineer"},
            )
            await session.commit()
            provenance_id = first.id

        async with database.session() as session:
            refreshed = await observe_job_provenance(
                session,
                job_id=job_id,
                source_id=source_id,
                source_job_id="external-42",
                source_url="https://arbeitnow.example.com/jobs/42-updated",
                seen_at=last_seen_at,
            )
            await session.commit()

        async with database.session() as session:
            provenance_count = await session.scalar(select(func.count()).select_from(JobProvenance))
            job_count = await session.scalar(select(func.count()).select_from(Job))

        assert refreshed.id == provenance_id
        assert refreshed.job_id == job_id
        assert refreshed.first_seen_at == first_seen_at
        assert refreshed.last_seen_at == last_seen_at
        assert refreshed.source_url == "https://arbeitnow.example.com/jobs/42-updated"
        assert refreshed.raw_payload == {"title": "Data Engineer"}
        assert provenance_count == 1
        assert job_count == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_provenance_rejects_reversed_seen_range(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        job_id, [source_id] = await create_job_and_sources(database, ["arbeitnow"])

        with pytest.raises(IntegrityError):
            async with database.session() as session:
                session.add(
                    JobProvenance(
                        job_id=job_id,
                        source_id=source_id,
                        source_job_id="external-42",
                        source_url="https://arbeitnow.example.com/jobs/42",
                        first_seen_at=datetime(2026, 8, 19, tzinfo=UTC),
                        last_seen_at=datetime(2026, 8, 18, tzinfo=UTC),
                    )
                )
                await session.commit()

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_observe_provenance_requires_timezone(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        job_id, [source_id] = await create_job_and_sources(database, ["arbeitnow"])

        async with database.session() as session:
            with pytest.raises(ValueError, match="timezone-aware"):
                await observe_job_provenance(
                    session,
                    job_id=job_id,
                    source_id=source_id,
                    source_job_id="external-42",
                    source_url="https://arbeitnow.example.com/jobs/42",
                    seen_at=datetime(2026, 8, 18),
                )

    run_database_test(database_url, exercise)
