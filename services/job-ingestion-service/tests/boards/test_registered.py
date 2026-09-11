import asyncio
from typing import Any

import pytest
from platform_db.models.boards import BoardStatus, JobBoard
from pydantic import PostgresDsn

from job_ingestion.boards.registered import polled_slugs
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration, ensure_source
from tests.boards.fakes import FAKE_BASE_URL
from tests.support.catalog import with_empty_catalog


def run_database_test(database_url: PostgresDsn, test: Any) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


@pytest.mark.integration
def test_polled_slugs_are_confirmed_named_and_pinned_never_blocked(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            source = await ensure_source(
                session,
                SourceRegistration(key="fake", display_name="Fake Boards", base_url=FAKE_BASE_URL),
            )
            for slug, status, pinned in (
                ("candidate-co", BoardStatus.CANDIDATE, False),
                ("confirmed-co", BoardStatus.CONFIRMED, False),
                ("named-co", BoardStatus.NAMED, False),
                ("wrong-co", BoardStatus.WRONG_COMPANY, False),
                ("not-found-co", BoardStatus.NOT_FOUND, False),
                ("pinned-not-found-co", BoardStatus.NOT_FOUND, True),
                ("unreachable-co", BoardStatus.UNREACHABLE, False),
                ("inactive-co", BoardStatus.INACTIVE, False),
                ("blocked-co", BoardStatus.BLOCKED, False),
                ("pinned-blocked-co", BoardStatus.BLOCKED, True),
            ):
                session.add(JobBoard(source_id=source.id, slug=slug, status=status, pinned=pinned))
            await session.commit()

            slugs = await polled_slugs(session, "fake")

        # A blocked row is never polled even if pinned: block overrules everything.
        assert slugs == ("confirmed-co", "named-co", "pinned-not-found-co")

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_source_with_no_row_polls_nothing(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            slugs = await polled_slugs(session, "nothing-registered")

        assert slugs == ()

    run_database_test(database_url, exercise)
