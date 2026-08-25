import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from platform_db.base import Base
from platform_db.models import (
    Company,
    Job,
    JobSkill,
    JobSkillMention,
    SkillAliasVersion,
    SkillConcept,
)
from pydantic import PostgresDsn
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.db.session import Database

pytestmark = pytest.mark.integration


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def clear(database: Database) -> None:
        async with database.session() as session:
            await session.execute(delete(JobSkillMention))
            await session.execute(delete(JobSkill))
            await session.execute(delete(Job))
            await session.execute(delete(Company))
            await session.execute(delete(SkillAliasVersion))
            await session.execute(delete(SkillConcept))
            await session.commit()

    async def run() -> None:
        database = Database(database_url)
        try:
            await clear(database)
            await test(database)
        finally:
            await clear(database)
            await database.dispose()

    asyncio.run(run())


async def create_job_skill_prerequisites(
    database: Database,
) -> tuple[Job, SkillConcept, SkillAliasVersion]:
    company = Company(display_name="Acme GmbH")
    job = Job(
        company=company,
        title="Data Engineer",
        description="Build PostgreSQL data pipelines.",
        application_url="https://example.com/jobs/data-engineer",
    )
    concept = SkillConcept(preferred_label="PostgreSQL")
    alias_version = SkillAliasVersion(version="2026.08.25.1")

    async with database.session() as session:
        session.add_all([job, concept, alias_version])
        await session.commit()

    return job, concept, alias_version


def test_job_skill_models_use_shared_metadata() -> None:
    assert JobSkill.metadata is Base.metadata
    assert JobSkillMention.metadata is Base.metadata


def test_one_job_cannot_carry_the_same_concept_twice(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        job, concept, alias_version = await create_job_skill_prerequisites(database)

        with pytest.raises(IntegrityError):
            async with database.session() as session:
                session.add_all(
                    [
                        JobSkill(
                            job_id=job.id,
                            concept_id=concept.id,
                            alias_version=alias_version.version,
                            surface_form="Postgres",
                        ),
                        JobSkill(
                            job_id=job.id,
                            concept_id=concept.id,
                            alias_version=alias_version.version,
                            surface_form="PostgreSQL",
                        ),
                    ]
                )
                await session.commit()

    run_database_test(database_url, exercise)


def test_deleting_job_cascades_to_skills_and_mentions(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        job, concept, alias_version = await create_job_skill_prerequisites(database)
        observed_at = datetime(2026, 8, 25, tzinfo=UTC)

        async with database.session() as session:
            session.add_all(
                [
                    JobSkill(
                        job_id=job.id,
                        concept_id=concept.id,
                        alias_version=alias_version.version,
                        surface_form="PostgreSQL",
                    ),
                    JobSkillMention(
                        job_id=job.id,
                        surface_form="TimescaleDB",
                        normalized_form="timescaledb",
                        occurrences=1,
                        first_seen_at=observed_at,
                        last_seen_at=observed_at,
                        extractor_version="1.0.0",
                        alias_version=alias_version.version,
                        evidence={"start": 6, "end": 17},
                    ),
                ]
            )
            await session.commit()

        async with database.session() as session:
            await session.execute(delete(Job).where(Job.id == job.id))
            await session.commit()

        async with database.session() as session:
            skill_count = await session.scalar(select(func.count()).select_from(JobSkill))
            mention_count = await session.scalar(
                select(func.count()).select_from(JobSkillMention)
            )

        assert skill_count == 0
        assert mention_count == 0

    run_database_test(database_url, exercise)


def test_concept_in_use_by_job_cannot_be_deleted(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        job, concept, alias_version = await create_job_skill_prerequisites(database)

        async with database.session() as session:
            session.add(
                JobSkill(
                    job_id=job.id,
                    concept_id=concept.id,
                    alias_version=alias_version.version,
                    surface_form="Postgres",
                )
            )
            await session.commit()

        with pytest.raises(IntegrityError):
            async with database.session() as session:
                await session.execute(delete(SkillConcept).where(SkillConcept.id == concept.id))
                await session.commit()

        async with database.session() as session:
            stored = await session.scalar(
                select(SkillConcept).where(SkillConcept.id == concept.id)
            )

        assert stored is not None

    run_database_test(database_url, exercise)
