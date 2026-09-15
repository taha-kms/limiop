import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from platform_db.models import Job, JobSource
from pydantic import PostgresDsn
from sqlalchemy import select

from job_ingestion.config import Environment, Settings
from job_ingestion.database import Database
from job_ingestion.jobicy.client import JobicyClient, JobicyConfig
from job_ingestion.jobicy.normalizer import PRECEDENCE
from job_ingestion.jobicy.pipeline import build_run, ingest_jobicy
from tests.support.catalog import with_empty_catalog

FIXTURES = Path(__file__).parent / "fixtures"
FAST_CONFIG = JobicyConfig(retry_backoff_seconds=0.0)


def feed_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads((FIXTURES / "remote_jobs.json").read_text())
    return body


def responding(
    *responses: httpx2.Response | Exception,
) -> Callable[[httpx2.Request], httpx2.Response]:
    remaining: Iterator[httpx2.Response | Exception] = iter(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        outcome = next(remaining)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return handler


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


def settings_for(database_url: PostgresDsn) -> Settings:
    return Settings(environment=Environment.TEST, database_url=database_url)


async def stored_titles(database: Database) -> list[str]:
    async with database.session() as session:
        return list(await session.scalars(select(Job.title).order_by(Job.title)))


@pytest.mark.integration
def test_the_fixture_page_ingests_into_the_catalog(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        client = JobicyClient(
            FAST_CONFIG,
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(responding(httpx2.Response(200, json=feed_body())))
            ),
        )
        summary = await build_run(client, 50).execute(database)

        assert summary.source_key == "jobicy"
        assert summary.fetched == 3
        assert summary.created == 3
        assert summary.updated == 0
        assert summary.skipped == 0
        assert summary.failures == ()
        assert summary.processing_complete is True
        assert summary.reached_the_end is True

        async with database.session() as session:
            source = (await session.scalars(select(JobSource))).one()

        assert source.key == "jobicy"
        assert source.precedence == PRECEDENCE
        assert await stored_titles(database) == [
            "Chief Technology Officer",
            "SVP, Product",
            "Senior DevOps Lead",
        ]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_running_twice_creates_nothing_new(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        for expected_created, expected_skipped in ((3, 0), (0, 3)):
            client = JobicyClient(
                FAST_CONFIG,
                http_client=httpx2.AsyncClient(
                    transport=httpx2.MockTransport(
                        responding(httpx2.Response(200, json=feed_body()))
                    )
                ),
            )
            summary = await build_run(client, 50).execute(database)

            assert summary.created == expected_created
            assert summary.skipped == expected_skipped

        assert len(await stored_titles(database)) == 3

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_one_bad_record_does_not_hide_the_good_ones(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        body = feed_body()
        del body["jobs"][1]["companyName"]
        client = JobicyClient(
            FAST_CONFIG,
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(responding(httpx2.Response(200, json=body)))
            ),
        )
        summary = await build_run(client, 50).execute(database)

        assert summary.fetched == 3
        assert summary.created == 2
        assert summary.failed == 1
        assert summary.processing_complete is False

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_entry_point_runs_against_the_configured_database(
    database_url: PostgresDsn,
) -> None:
    """The scheduler entry point owns the engine and the client, so this
    exercises it end to end with only the outbound transport replaced."""

    async def exercise(database: Database) -> None:
        summary = await ingest_jobicy(
            config=FAST_CONFIG,
            settings=settings_for(database_url),
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(responding(httpx2.Response(200, json=feed_body())))
            ),
        )

        assert summary.source_key == "jobicy"
        assert summary.created == 3
        assert summary.processing_complete is True
        assert len(await stored_titles(database)) == 3

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_entry_point_reports_an_unreachable_provider(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest_jobicy(
            config=FAST_CONFIG,
            settings=settings_for(database_url),
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(
                    responding(*[httpx2.ConnectError("refused")] * FAST_CONFIG.max_attempts)
                )
            ),
        )

        assert summary.fetched == 0
        assert summary.reached_the_end is False

    run_database_test(database_url, exercise)


def test_a_run_must_have_a_record_budget() -> None:
    client = JobicyClient(FAST_CONFIG, http_client=httpx2.AsyncClient())
    with pytest.raises(ValueError, match="max_records"):
        build_run(client, 0)


@pytest.mark.integration
def test_the_run_registers_the_configured_source(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        client = JobicyClient(
            JobicyConfig(base_url="https://example.test/api"),
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(responding(httpx2.Response(200, json={"jobs": []})))
            ),
        )
        run = build_run(client, 50)

        assert run.source.key == "jobicy"
        assert run.source.display_name == "Jobicy"
        assert run.source.base_url == "https://example.test/api"
        assert run.source.precedence == PRECEDENCE
        assert run.client.source_key == run.source.key

        await run.execute(database)

    run_database_test(database_url, exercise)
