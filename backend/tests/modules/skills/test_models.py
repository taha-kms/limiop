import asyncio
from collections.abc import Awaitable, Callable

import pytest
from platform_db.base import Base
from platform_db.models import SkillAliasVersion, SkillConcept, SkillSurfaceForm
from pydantic import PostgresDsn
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.session import Database

pytestmark = pytest.mark.integration


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def clear(database: Database) -> None:
        async with database.session() as session:
            await session.execute(delete(SkillSurfaceForm))
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


def test_skill_models_use_shared_metadata() -> None:
    assert SkillConcept.metadata is Base.metadata


def test_concepts_and_versioned_surface_forms_round_trip(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        without_esco = SkillConcept(preferred_label="PostgreSQL")
        with_esco = SkillConcept(
            preferred_label="Mapped skill",
            esco_uri="https://data.europa.eu/esco/skill/example",
        )
        alias_version = SkillAliasVersion(version="2026.08.24.1")

        async with database.session() as session:
            session.add_all([without_esco, with_esco, alias_version])
            await session.flush()
            session.add_all(
                [
                    SkillSurfaceForm(
                        alias_version=alias_version.version,
                        concept_id=without_esco.id,
                        surface_form="Postgres",
                        normalized_form="postgres",
                    ),
                    SkillSurfaceForm(
                        alias_version=alias_version.version,
                        concept_id=with_esco.id,
                        surface_form="AI",
                        normalized_form="ai",
                    ),
                    SkillSurfaceForm(
                        alias_version=alias_version.version,
                        concept_id=without_esco.id,
                        surface_form="AI",
                        normalized_form="ai",
                    ),
                ]
            )
            await session.commit()

        async with database.session() as session:
            concepts = (await session.execute(select(SkillConcept))).scalars().all()
            ambiguous = (
                (
                    await session.execute(
                        select(SkillSurfaceForm).where(
                            SkillSurfaceForm.alias_version == "2026.08.24.1",
                            SkillSurfaceForm.normalized_form == "ai",
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert {concept.esco_uri for concept in concepts} == {
            None,
            "https://data.europa.eu/esco/skill/example",
        }
        assert len(ambiguous) == 2
        assert all(form.alias_version == "2026.08.24.1" for form in ambiguous)

    run_database_test(database_url, exercise)


def test_one_concept_mapping_cannot_be_duplicated_within_a_version(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        concept = SkillConcept(preferred_label="PostgreSQL")
        alias_version = SkillAliasVersion(version="2026.08.24.1")
        async with database.session() as session:
            session.add_all([concept, alias_version])
            await session.flush()
            session.add_all(
                [
                    SkillSurfaceForm(
                        alias_version=alias_version.version,
                        concept_id=concept.id,
                        surface_form="Postgres",
                        normalized_form="postgres",
                    ),
                    SkillSurfaceForm(
                        alias_version=alias_version.version,
                        concept_id=concept.id,
                        surface_form="POSTGRES",
                        normalized_form="postgres",
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

    run_database_test(database_url, exercise)
