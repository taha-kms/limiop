import asyncio
import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import PostgresDsn
from sqlalchemy import select

from app.core.config import Environment, Settings
from app.db.session import Database
from app.modules.ingestion.contracts import IngestionStage, IngestionSummary, RecordFailure
from app.modules.ingestion.greenhouse.client import GreenhouseClient, GreenhouseConfig
from app.modules.ingestion.greenhouse.pipeline import (
    PRECEDENCE,
    build_run,
    ingest_greenhouse,
    with_board_failures,
)
from app.modules.jobs.models import Job, JobSource
from tests.support.catalog import with_empty_catalog

FIXTURE = Path(__file__).parent / "fixtures" / "board.json"


def board_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(FIXTURE.read_text())
    return body


def responding(*replies: httpx2.Response | Exception) -> httpx2.AsyncClient:
    remaining = iter(replies)

    def handle(request: httpx2.Request) -> httpx2.Response:
        reply = next(remaining)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


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


def test_board_failures_are_added_to_what_the_run_reports() -> None:
    """The generic run only sees pages it was handed, so a skipped board is invisible."""
    summary = IngestionSummary(source_key="greenhouse", fetched=2, created=2)
    client = GreenhouseClient(GreenhouseConfig(), http_client=responding())
    client.failures.append(RecordFailure(stage=IngestionStage.FETCH, reason="board gone"))

    combined = with_board_failures(summary, client)

    assert combined.failures[0].reason == "board gone"
    assert combined.is_complete is False


def test_a_run_with_every_board_read_reports_nothing_extra() -> None:
    summary = IngestionSummary(source_key="greenhouse", fetched=2, created=2)
    client = GreenhouseClient(GreenhouseConfig(), http_client=responding())

    assert with_board_failures(summary, client) is summary


@pytest.mark.integration
def test_a_board_ingests_into_the_catalogue(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        client = GreenhouseClient(
            GreenhouseConfig(boards=("hudl",)),
            http_client=responding(httpx2.Response(200, json=board_body())),
        )
        summary = await build_run(client, 50).execute(database)

        assert summary.fetched == 2
        assert summary.created == 2
        assert summary.is_complete

        async with database.session() as session:
            stored = (await session.scalars(select(Job))).all()
            source = (await session.scalars(select(JobSource))).one()

        assert len(stored) == 2
        assert source.key == "greenhouse"
        # Ranked above the aggregator, so the employer's own account wins.
        assert source.precedence == PRECEDENCE
        assert all("<" not in job.description for job in stored)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_running_twice_creates_nothing_the_second_time(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        for expected_created, expected_skipped in ((2, 0), (0, 2)):
            client = GreenhouseClient(
                GreenhouseConfig(boards=("hudl",)),
                http_client=responding(httpx2.Response(200, json=board_body())),
            )
            summary = await build_run(client, 50).execute(database)
            assert summary.created == expected_created
            assert summary.skipped == expected_skipped

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_one_failed_board_does_not_stop_the_others(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        client = GreenhouseClient(
            GreenhouseConfig(boards=("gone", "hudl"), retry_backoff_seconds=0.0),
            http_client=responding(
                httpx2.Response(404),
                httpx2.Response(200, json=board_body()),
            ),
        )
        summary = with_board_failures(await build_run(client, 50).execute(database), client)

        assert summary.created == 2
        assert len(summary.failures) == 1
        # A run missing a whole company is not a complete run.
        assert summary.is_complete is False

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_entry_point_runs_against_the_configured_database(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest_greenhouse(
            config=GreenhouseConfig(boards=("hudl",)),
            settings=settings_for(database_url),
            http_client=responding(httpx2.Response(200, json=board_body())),
        )

        assert summary.source_key == "greenhouse"
        assert summary.created == 2

        async with database.session() as session:
            assert len((await session.scalars(select(Job))).all()) == 2

    run_database_test(database_url, exercise)


def test_the_default_configuration_names_the_boards_it_reads() -> None:
    """Listed rather than discovered, so adding one stays a deliberate act."""
    from app.modules.ingestion.greenhouse.pipeline import DEFAULT_BOARDS, default_config

    config = default_config()

    assert config.boards == DEFAULT_BOARDS
    assert config.boards
    assert config.base_url.startswith("https://")
