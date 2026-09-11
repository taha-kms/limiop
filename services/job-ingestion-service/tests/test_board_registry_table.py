"""The board registry table: what the migration seeds and what it enforces."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from platform_db.models import JobSource
from platform_db.models.boards import BoardStatus, JobBoard
from pydantic import PostgresDsn
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from job_ingestion.database import Database
from tests.support.catalog import with_empty_catalog

REPOSITORY_ROOT = Path(__file__).parents[3]
PLATFORM_DB_ROOT = REPOSITORY_ROOT / "platform" / "db"

SHIPPED_GREENHOUSE_SLUGS = {"anthropic", "datadog", "hudl"}


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


def source_for(key: str = "greenhouse") -> JobSource:
    return JobSource(
        key=key,
        display_name=key.title(),
        base_url=f"https://{key}.example.com",
    )


@pytest.mark.integration
def test_the_migration_seeds_the_shipped_greenhouse_boards(database_url: PostgresDsn) -> None:
    """Do not clear the catalogue: the assertion is about what the migration wrote.

    Alembic's `env.py` runs its own event loop, so the downgrade/upgrade calls
    stay outside `asyncio.run` here rather than inside the coroutine below.
    """
    platform_config = Config(PLATFORM_DB_ROOT / "alembic.ini")
    command.downgrade(platform_config, "0003_ingestion_runs")
    command.upgrade(platform_config, "head")

    async def query() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                rows = (
                    await session.scalars(
                        select(JobBoard)
                        .join(JobSource, JobBoard.source_id == JobSource.id)
                        .where(JobSource.key == "greenhouse")
                    )
                ).all()

                assert {board.slug for board in rows} == SHIPPED_GREENHOUSE_SLUGS
                assert all(board.pinned for board in rows)
                assert all(board.status is BoardStatus.CONFIRMED for board in rows)
                assert all(
                    board.evidence is not None and board.evidence["kind"] == "operator"
                    for board in rows
                )
        finally:
            await database.dispose()

    try:
        asyncio.run(query())
    finally:
        # Reset so the fixture's next `upgrade head` is a no-op.
        command.downgrade(platform_config, "0003_ingestion_runs")
        command.upgrade(platform_config, "head")


@pytest.mark.integration
def test_a_slug_is_unique_within_a_source(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            source = source_for()
            session.add(source)
            await session.flush()

            session.add(JobBoard(source_id=source.id, slug="acme"))
            await session.flush()

            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    session.add(JobBoard(source_id=source.id, slug="acme"))
                    await session.flush()

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_same_slug_may_exist_on_two_sources(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            first_source = source_for("greenhouse")
            second_source = source_for("polymer")
            session.add(first_source)
            session.add(second_source)
            await session.flush()

            session.add(JobBoard(source_id=first_source.id, slug="acme"))
            session.add(JobBoard(source_id=second_source.id, slug="acme"))
            await session.flush()

            rows = (await session.scalars(select(JobBoard))).all()
            assert len(rows) == 2

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_status_outside_the_vocabulary_is_refused(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            source = source_for()
            session.add(source)
            await session.flush()

            with pytest.raises(IntegrityError, match="ck_job_boards_status"):
                async with session.begin_nested():
                    await session.execute(
                        text(
                            "INSERT INTO job_boards (id, source_id, slug, status) "
                            "VALUES (gen_random_uuid(), :source_id, 'bogus-slug', 'bogus')"
                        ),
                        {"source_id": source.id},
                    )

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_defaults(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            source = source_for()
            session.add(source)
            await session.flush()

            board = JobBoard(source_id=source.id, slug="acme")
            session.add(board)
            await session.flush()

            assert board.status is BoardStatus.CANDIDATE
            assert board.pinned is False
            assert board.consecutive_failures == 0
            assert board.discovered_at is not None
            assert board.discovered_at.tzinfo is not None
            assert board.company is None

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_source_with_boards_cannot_be_deleted(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            source = source_for()
            session.add(source)
            await session.flush()

            session.add(JobBoard(source_id=source.id, slug="acme"))
            await session.flush()

            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.delete(source)
                    await session.flush()

    run_database_test(database_url, exercise)
