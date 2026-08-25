import asyncio
from collections.abc import Awaitable, Callable

import pytest
from platform_db.models import SkillAliasVersion, SkillConcept, SkillSurfaceForm
from pydantic import PostgresDsn
from sqlalchemy import delete, func, select, update

import app.modules.skills.loading as alias_loading
from app.db.session import Database
from app.modules.skills.loading import PublishedAliasConflictError, load_published_alias_table
from app.modules.skills.resolution import KnownSkillResolver, load_resolver

V1 = "2026.08.24.1"
V2 = "2026.08.25.1"

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


def test_loading_v2_is_complete_and_idempotent(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            first = await load_published_alias_table(session, V2)
            await session.commit()
            second = await load_published_alias_table(session, V2)
            await session.commit()

            concept_count = await session.scalar(select(func.count()).select_from(SkillConcept))
            version_count = await session.scalar(
                select(func.count()).select_from(SkillAliasVersion)
            )
            surface_form_count = await session.scalar(
                select(func.count()).select_from(SkillSurfaceForm)
            )

        assert first.loaded is True
        assert first.concepts_inserted == 56
        assert first.surface_forms_inserted == 182
        assert second.loaded is False
        assert second.concepts_inserted == second.surface_forms_inserted == 0
        assert (concept_count, version_count, surface_form_count) == (56, 1, 182)

    run_database_test(database_url, exercise)


def test_a_published_version_refuses_different_artifact_content(
    database_url: PostgresDsn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = load_resolver(V2).document
    changed_concept = original.concepts[0].model_copy(
        update={"preferred_label": f"{original.concepts[0].preferred_label} tampered"}
    )
    tampered = original.model_copy(update={"concepts": (changed_concept, *original.concepts[1:])})

    async def exercise(database: Database) -> None:
        async with database.session() as session:
            await load_published_alias_table(session, V2)
            await session.commit()

            monkeypatch.setattr(
                alias_loading,
                "load_resolver",
                lambda _version: KnownSkillResolver(tampered),
            )
            with pytest.raises(
                PublishedAliasConflictError,
                match=rf"published alias version {V2}.*preferred_label differs",
            ):
                await load_published_alias_table(session, V2)

            stored_label = await session.scalar(
                select(SkillConcept.preferred_label).where(
                    SkillConcept.id == original.concepts[0].id
                )
            )

        assert stored_label == original.concepts[0].preferred_label

    run_database_test(database_url, exercise)


def test_published_versions_coexist_with_attributable_surface_forms(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            await load_published_alias_table(session, V1)
            await session.commit()
            await load_published_alias_table(session, V2)
            await session.commit()

            versions = set(await session.scalars(select(SkillAliasVersion.version)))
            count_rows = (
                await session.execute(
                    select(SkillSurfaceForm.alias_version, func.count())
                    .group_by(SkillSurfaceForm.alias_version)
                    .order_by(SkillSurfaceForm.alias_version)
                )
            ).all()
            counts: dict[str, int] = {version: count for version, count in count_rows}

        assert versions == {V1, V2}
        assert counts == {V1: 22, V2: 182}

    run_database_test(database_url, exercise)


def test_a_published_version_refuses_changed_surface_content(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            await load_published_alias_table(session, V2)
            await session.commit()
            await session.execute(
                update(SkillSurfaceForm)
                .where(
                    SkillSurfaceForm.alias_version == V2,
                    SkillSurfaceForm.surface_form == "deep learning",
                )
                .values(surface_form="tampered learning")
            )
            await session.commit()

            with pytest.raises(
                PublishedAliasConflictError,
                match=rf"published alias version {V2}.*surface-form row is missing",
            ):
                await load_published_alias_table(session, V2)

    run_database_test(database_url, exercise)
