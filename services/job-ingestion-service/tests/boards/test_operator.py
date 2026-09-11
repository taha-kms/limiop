import asyncio
from typing import Any

import pytest
from platform_db.models.boards import BoardStatus, JobBoard
from pydantic import PostgresDsn
from sqlalchemy import select

from job_ingestion.boards.operator import add_board, block_board, list_boards, unblock_board
from job_ingestion.boards.registered import polled_slugs
from job_ingestion.config import Environment, Settings
from job_ingestion.database import Database
from tests.boards.fakes import json_provider
from tests.support.catalog import with_empty_catalog


def run_database_test(database_url: PostgresDsn, test: Any) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


def settings_for(database_url: PostgresDsn) -> Settings:
    return Settings(environment=Environment.TEST, database_url=database_url)


@pytest.mark.integration
def test_add_creates_a_confirmed_pinned_row_and_the_source_on_a_fresh_database(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            board = await add_board(session, json_provider(), settings_for(database_url), "acme")
            await session.commit()

        assert board.status is BoardStatus.CONFIRMED
        assert board.pinned is True
        assert board.evidence is not None
        assert board.evidence["kind"] == "operator"
        assert board.verified_at is not None

        async with database.session() as session:
            slugs = await polled_slugs(session, "fake")

        assert slugs == ("acme",)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_add_overrides_a_wrong_company_row(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        provider = json_provider()
        settings = settings_for(database_url)
        async with database.session() as session:
            await add_board(session, provider, settings, "acme")
            await session.commit()

        async with database.session() as session:
            wrong = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()
            wrong.status = BoardStatus.WRONG_COMPANY
            wrong.pinned = False
            await session.commit()

        async with database.session() as session:
            board = await add_board(session, provider, settings, "acme")
            await session.commit()

        assert board.status is BoardStatus.CONFIRMED
        assert board.pinned is True

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_block_on_an_unknown_slug_creates_a_blocked_row_absent_from_polling(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        provider = json_provider()
        settings = settings_for(database_url)
        async with database.session() as session:
            board = await block_board(session, provider, settings, "globex")
            await session.commit()

        assert board.status is BoardStatus.BLOCKED
        assert board.pinned is False

        async with database.session() as session:
            slugs = await polled_slugs(session, "fake")

        assert slugs == ()

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_block_on_a_pinned_row_clears_the_pin(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        provider = json_provider()
        settings = settings_for(database_url)
        async with database.session() as session:
            await add_board(session, provider, settings, "acme")
            await session.commit()

        async with database.session() as session:
            board = await block_board(session, provider, settings, "acme")
            await session.commit()

        assert board.status is BoardStatus.BLOCKED
        assert board.pinned is False

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_unblock_returns_a_board_to_candidate(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        provider = json_provider()
        settings = settings_for(database_url)
        async with database.session() as session:
            await block_board(session, provider, settings, "acme")
            await session.commit()

        async with database.session() as session:
            board = await unblock_board(session, provider, "acme")
            await session.commit()

        assert board.status is BoardStatus.CANDIDATE

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_unblock_on_an_unregistered_slug_is_refused(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        provider = json_provider()
        async with database.session() as session:
            with pytest.raises(ValueError, match="no board nope registered for fake"):
                await unblock_board(session, provider, "nope")

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_list_returns_every_row(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        provider = json_provider()
        settings = settings_for(database_url)
        async with database.session() as session:
            await add_board(session, provider, settings, "acme")
            await block_board(session, provider, settings, "globex")
            await session.commit()

        async with database.session() as session:
            rows = await list_boards(session, provider)

        assert [row["slug"] for row in rows] == ["acme", "globex"]
        acme = next(row for row in rows if row["slug"] == "acme")
        assert acme["status"] == "confirmed"
        assert acme["pinned"] is True
        assert acme["company"] is None
        assert acme["consecutive_failures"] == 0

    run_database_test(database_url, exercise)
