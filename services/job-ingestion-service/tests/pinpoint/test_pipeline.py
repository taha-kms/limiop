import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from platform_db.models import Job, JobSource
from platform_db.models.catalog import WorkplaceType
from pydantic import PostgresDsn
from sqlalchemy import select

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.pipeline import build_run
from job_ingestion.boards.registered import polled_slugs
from job_ingestion.config import Environment, Settings
from job_ingestion.database import Database
from job_ingestion.pinpoint.pipeline import ingest_pinpoint
from job_ingestion.pinpoint.provider import PINPOINT
from job_ingestion.pinpoint.source import PRECEDENCE
from tests.boards.fakes import ok, responding
from tests.support.catalog import with_empty_catalog

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "postings.json"
REMOTE_FIXTURE = FIXTURES / "remote_posting.json"


def fixture_body(fixture: Path = FIXTURE) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(fixture.read_text())
    return body


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
def test_a_board_ingests_into_the_catalogue(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        client = BoardClient(
            PINPOINT,
            BoardConfig(boards=("workwithus",)),
            http_client=responding(ok(fixture_body())),
        )
        summary = await build_run(client, 50).execute(database)

        assert summary.created == 1
        assert summary.source_key == "pinpoint"

        async with database.session() as session:
            stored = (await session.scalars(select(Job))).all()
            source = (await session.scalars(select(JobSource))).one()

        assert len(stored) == 1
        assert source.key == "pinpoint"
        # Ranked with Greenhouse and Polymer: an employer's own board over the aggregator.
        assert source.precedence == PRECEDENCE

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_posting_with_null_optional_fields_is_stored(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        client = BoardClient(
            PINPOINT,
            BoardConfig(boards=("workwithus",)),
            http_client=responding(ok(fixture_body(REMOTE_FIXTURE))),
        )
        summary = await build_run(client, 50).execute(database)

        assert summary.created == 1
        assert summary.failures == ()

        async with database.session() as session:
            stored = (await session.scalars(select(Job))).one()

        assert stored.location == "Multiple locations"
        assert stored.workplace_type is WorkplaceType.UNSPECIFIED

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_entry_point_runs_against_the_configured_database(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest_pinpoint(
            config=BoardConfig(boards=("workwithus",)),
            settings=settings_for(database_url),
            http_client=responding(ok(fixture_body())),
        )

        assert summary.source_key == "pinpoint"
        assert summary.created == 1

        async with database.session() as session:
            assert len((await session.scalars(select(Job))).all()) == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_nothing_is_polled_until_a_board_is_registered(database_url: PostgresDsn) -> None:
    """The feed never states the company; nothing ships as a default board either way."""

    async def exercise(database: Database) -> None:
        async with database.session() as session:
            assert await polled_slugs(session, "pinpoint") == ()

    run_database_test(database_url, exercise)
