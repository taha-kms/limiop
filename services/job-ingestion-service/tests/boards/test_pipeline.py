import asyncio
from typing import Any

import httpx2
import pytest
from platform_db.models import Job, JobSource
from pydantic import JsonValue, PostgresDsn
from sqlalchemy import select

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.pipeline import (
    build_run,
    configured_base_url,
    configured_boards,
    default_config,
    ingest_board_source,
    with_board_failures,
)
from job_ingestion.config import Environment, Settings
from job_ingestion.contracts import IngestionStage, IngestionSummary, RecordFailure
from job_ingestion.database import Database
from tests.boards.fakes import FAKE_BASE_URL, jobs, json_provider, ok, responding
from tests.support.catalog import with_empty_catalog


def configured(**block: JsonValue) -> Settings:
    return Settings(environment=Environment.TEST, source_config={"fake": block})


def test_the_default_configuration_reads_the_providers_boards() -> None:
    config = default_config(json_provider(), Settings(environment=Environment.TEST))

    assert config.boards == ("acme",)
    assert config.base_url == FAKE_BASE_URL


def test_configured_boards_replace_the_shipped_ones() -> None:
    assert configured_boards(json_provider(), configured(boards=["globex"])) == ("globex",)


def test_no_configured_boards_means_the_shipped_ones() -> None:
    assert configured_boards(json_provider(), configured(boards=[])) == ("acme",)
    assert configured_boards(json_provider(), configured()) == ("acme",)


@pytest.mark.parametrize(
    "boards",
    [
        pytest.param("acme", id="one name rather than a list"),
        pytest.param([1], id="a list of something other than names"),
    ],
)
def test_a_board_list_that_is_not_one_is_refused(boards: JsonValue) -> None:
    with pytest.raises(ValueError, match=r"fake.boards must be a list of board names"):
        configured_boards(json_provider(), configured(boards=boards))


def test_a_configured_base_url_replaces_the_providers() -> None:
    """A regional host is a deployment fact, not a code change."""
    assert (
        configured_base_url(json_provider(), configured(base_url="https://eu.example.test"))
        == "https://eu.example.test"
    )
    assert default_config(
        json_provider(), configured(base_url="https://eu.example.test")
    ).base_url == ("https://eu.example.test")


def test_an_absent_base_url_means_the_providers() -> None:
    assert configured_base_url(json_provider(), configured()) == FAKE_BASE_URL


@pytest.mark.parametrize("value", [pytest.param(1, id="not text"), pytest.param("  ", id="blank")])
def test_a_base_url_that_is_not_one_is_refused(value: JsonValue) -> None:
    with pytest.raises(ValueError, match=r"fake.base_url must be a URL"):
        configured_base_url(json_provider(), configured(base_url=value))


def test_board_failures_are_added_to_what_the_run_reports() -> None:
    summary = IngestionSummary(source_key="fake", fetched=2, created=2)
    client = BoardClient(json_provider(), http_client=responding())
    client.failures.append(RecordFailure(stage=IngestionStage.FETCH, reason="board gone"))

    combined = with_board_failures(summary, client)

    assert combined.failures[0].reason == "board gone"
    assert combined.processing_complete is False


def test_a_run_with_every_board_read_reports_nothing_extra() -> None:
    summary = IngestionSummary(source_key="fake", fetched=2, created=2)
    client = BoardClient(json_provider(), http_client=responding())

    assert with_board_failures(summary, client) is summary


def run_database_test(database_url: PostgresDsn, test: Any) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


@pytest.mark.integration
def test_a_fake_provider_ingests_under_its_own_source(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        client = BoardClient(
            json_provider(),
            BoardConfig(boards=("acme",)),
            http_client=responding(ok(jobs(1, 2))),
        )
        summary = await build_run(client, 50).execute(database)

        assert summary.fetched == 2
        assert summary.created == 2

        async with database.session() as session:
            source = (await session.scalars(select(JobSource))).one()
            stored = (await session.scalars(select(Job))).all()

        assert source.key == "fake"
        assert source.display_name == "Fake Boards"
        assert source.base_url == FAKE_BASE_URL
        assert source.precedence == 15
        assert len(stored) == 2

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_entry_point_runs_any_provider(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest_board_source(
            json_provider(),
            config=BoardConfig(boards=("acme",)),
            settings=Settings(environment=Environment.TEST, database_url=database_url),
            http_client=responding(httpx2.Response(200, json=jobs(1))),
        )

        assert summary.source_key == "fake"
        assert summary.created == 1

    run_database_test(database_url, exercise)
