import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest
from platform_db.models import Company, Job, JobBoard, JobProvenance, JobSource
from pydantic import PostgresDsn
from sqlalchemy import delete, select

from job_ingestion.config import Settings
from job_ingestion.contracts import IngestionStage, IngestionSummary
from job_ingestion.database import Database
from job_ingestion.remotive.client import RemotiveConfig
from job_ingestion.remotive.pipeline import ingest_remotive, remotive_run

FIXTURES = Path(__file__).parent / "fixtures"
FAST_CONFIG = RemotiveConfig(retry_backoff_seconds=0.0)
RUN_AT = datetime(2026, 9, 15, 12, tzinfo=UTC)


def fixture_jobs() -> list[dict[str, Any]]:
    body: dict[str, Any] = json.loads((FIXTURES / "remote_jobs.json").read_text())
    jobs: list[dict[str, Any]] = body["jobs"]
    return jobs


def page(records: list[dict[str, Any]]) -> httpx2.Response:
    return httpx2.Response(200, json={"jobs": records})


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
    async def clear(database: Database) -> None:
        async with database.session() as session:
            await session.execute(delete(JobProvenance))
            await session.execute(delete(Job))
            await session.execute(delete(JobBoard))
            await session.execute(delete(Company))
            await session.execute(delete(JobSource))
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


async def ingest(
    database: Database,
    handler: Callable[[httpx2.Request], httpx2.Response],
    *,
    config: RemotiveConfig = FAST_CONFIG,
    max_records: int = 100,
) -> IngestionSummary:
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    run = remotive_run(config, http_client=http_client, max_records=max_records)
    try:
        return await run.execute(database, clock=lambda: RUN_AT)
    finally:
        await http_client.aclose()


async def stored_titles(database: Database) -> list[str]:
    async with database.session() as session:
        return list(await session.scalars(select(Job.title).order_by(Job.title)))


@pytest.mark.integration
def test_a_full_jobs_page_reaches_postgresql(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(database, responding(page(fixture_jobs())))

        assert summary.source_key == "remotive"
        assert summary.fetched == 3
        assert summary.created == 3
        assert summary.updated == 0
        assert summary.skipped == 0
        assert summary.failures == ()
        assert summary.processing_complete is True
        assert summary.source_exhausted is True
        assert await stored_titles(database) == [
            "AI Response Evaluator",
            "Inside Sales Contractor",
            "Remote Office Assistant",
        ]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_running_twice_creates_nothing_new(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        records = fixture_jobs()
        first = await ingest(database, responding(page(records)))
        second = await ingest(database, responding(page(records)))

        assert first.created == 3
        assert second.created == 0
        assert second.skipped == 3
        assert second.processing_complete is True
        assert len(await stored_titles(database)) == 3

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_changed_posting_updates_rather_than_duplicates(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        records = fixture_jobs()
        await ingest(database, responding(page(records)))

        revised = [dict(records[0], description="<p>Now hiring urgently.</p>"), *records[1:]]
        summary = await ingest(database, responding(page(revised)))

        assert summary.updated == 1
        assert summary.skipped == 2
        assert summary.created == 0
        assert len(await stored_titles(database)) == 3

        async with database.session() as session:
            descriptions = list(await session.scalars(select(Job.description)))

        assert any("Now hiring urgently." in description for description in descriptions)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_one_bad_record_does_not_hide_the_good_ones(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        records = fixture_jobs()
        broken = dict(records[1])
        del broken["company_name"]

        summary = await ingest(database, responding(page([records[0], broken, records[2]])))

        assert summary.fetched == 3
        assert summary.created == 2
        assert summary.failed == 1
        assert summary.processing_complete is False
        assert summary.failures[0].stage is IngestionStage.VALIDATE
        assert "company_name" in summary.failures[0].reason

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_record_rejected_by_normalization_names_that_stage(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        records = fixture_jobs()
        empty_after_stripping = dict(records[1], description="<div><span></span></div>")

        summary = await ingest(
            database, responding(page([records[0], empty_after_stripping, records[2]]))
        )

        assert summary.created == 2
        assert summary.failures[0].stage is IngestionStage.NORMALIZE
        assert summary.failures[0].source_job_id == str(records[1]["id"])

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_immediately_unreachable_provider_reports_an_empty_run(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(
            database,
            responding(*[httpx2.ConnectError("refused")] * FAST_CONFIG.max_attempts),
        )

        assert summary.fetched == 0
        assert summary.created == 0
        assert summary.failed == 1
        assert summary.failures[0].stage is IngestionStage.FETCH
        assert summary.source_exhausted is False

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unusable_response_ends_the_run(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(database, responding(httpx2.Response(503, text="down")))

        assert summary.fetched == 0
        assert summary.failures[0].stage is IngestionStage.FETCH
        assert "503" in summary.failures[0].reason

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_run_stops_at_its_record_budget(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(database, responding(page(fixture_jobs())), max_records=1)

        assert summary.fetched == 1
        assert summary.created == 1
        assert summary.stopped_at_budget is True
        assert len(await stored_titles(database)) == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_provenance_records_the_run_time(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, responding(page(fixture_jobs()[:1])))

        async with database.session() as session:
            provenance = (await session.scalars(select(JobProvenance))).one()

        assert provenance.first_seen_at == RUN_AT
        assert provenance.last_seen_at == RUN_AT
        assert provenance.raw_payload is not None
        assert provenance.raw_payload["id"] == 1680495

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_empty_feed_is_a_complete_run(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(database, responding(page([])))

        assert summary.fetched == 0
        assert summary.processing_complete is True
        assert summary.failures == ()

    run_database_test(database_url, exercise)


def test_a_run_must_have_a_record_budget() -> None:
    with pytest.raises(ValueError, match="max_records"):
        remotive_run(FAST_CONFIG, max_records=0)


def test_the_run_registers_the_configured_source() -> None:
    run = remotive_run(RemotiveConfig(base_url="https://example.test/api"))

    assert run.source.key == "remotive"
    assert run.source.display_name == "Remotive"
    assert run.source.base_url == "https://example.test/api"
    assert run.client.source_key == run.source.key


@pytest.mark.integration
def test_the_entry_point_runs_against_the_configured_database(database_url: PostgresDsn) -> None:
    """The scheduler entry point owns the engine and the client, so this
    exercises it end to end with only the outbound transport replaced."""

    async def exercise(database: Database) -> None:
        http_client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(responding(page(fixture_jobs())))
        )
        try:
            summary = await ingest_remotive(
                config=FAST_CONFIG,
                settings=Settings(database_url=PostgresDsn(str(database_url))),
                http_client=http_client,
            )
        finally:
            await http_client.aclose()

        assert summary.source_key == "remotive"
        assert summary.created == 3
        assert summary.processing_complete is True
        assert len(await stored_titles(database)) == 3

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_entry_point_reports_an_unreachable_provider(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        http_client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(
                responding(*[httpx2.ConnectError("refused")] * FAST_CONFIG.max_attempts)
            )
        )
        try:
            summary = await ingest_remotive(
                config=FAST_CONFIG,
                settings=Settings(database_url=PostgresDsn(str(database_url))),
                http_client=http_client,
            )
        finally:
            await http_client.aclose()

        assert summary.fetched == 0
        assert summary.failures[0].stage is IngestionStage.FETCH

    run_database_test(database_url, exercise)
