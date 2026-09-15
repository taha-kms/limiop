from datetime import UTC, datetime

import httpx2
import pytest
from platform_db.models import Job, JobProvenance
from pydantic import PostgresDsn
from sqlalchemy import select

from job_ingestion.config import Settings
from job_ingestion.contracts import IngestionStage, IngestionSummary
from job_ingestion.database import Database
from job_ingestion.himalayas.client import HimalayasConfig
from job_ingestion.himalayas.pipeline import himalayas_run, ingest_himalayas
from tests.boards.fakes import ok, responding
from tests.himalayas.support import feed_page, page_body, run_database_test

FAST_CONFIG = HimalayasConfig(retry_backoff_seconds=0.0)
RUN_AT = datetime(2026, 9, 15, 12, tzinfo=UTC)


async def ingest(
    database: Database,
    *replies: httpx2.Response | Exception,
    config: HimalayasConfig = FAST_CONFIG,
    max_records: int = 100,
) -> IngestionSummary:
    http_client = responding(*replies)
    run = himalayas_run(config, http_client=http_client, max_records=max_records)
    try:
        return await run.execute(database, clock=lambda: RUN_AT)
    finally:
        await http_client.aclose()


async def stored_titles(database: Database) -> list[str]:
    async with database.session() as session:
        return list(await session.scalars(select(Job.title).order_by(Job.title)))


@pytest.mark.integration
def test_two_pages_reach_postgresql_with_expiry_stored(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(
            database, ok(page_body("page_one.json")), ok(page_body("page_two.json"))
        )

        assert summary.source_key == "himalayas"
        assert summary.fetched == 4
        assert summary.created == 4
        assert summary.updated == 0
        assert summary.skipped == 0
        assert summary.failures == ()
        assert summary.processing_complete is True
        assert summary.reached_the_end is True

        async with database.session() as session:
            expiries = list(await session.scalars(select(Job.expires_at)))

        assert len(expiries) == 4
        assert all(expiry is not None for expiry in expiries)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_running_twice_creates_nothing_new(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        first = await ingest(
            database, ok(page_body("page_one.json")), ok(page_body("page_two.json"))
        )
        second = await ingest(
            database, ok(page_body("page_one.json")), ok(page_body("page_two.json"))
        )

        assert first.created == 4
        assert second.created == 0
        assert second.skipped == 4
        assert second.processing_complete is True
        assert len(await stored_titles(database)) == 4

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_one_bad_record_does_not_hide_the_good_ones(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        good, other = page_body("page_one.json")["jobs"]
        broken = dict(other)
        del broken["companyName"]

        summary = await ingest(database, ok(feed_page([good, broken])))

        assert summary.fetched == 2
        assert summary.created == 1
        assert summary.failed == 1
        assert summary.processing_complete is False
        assert summary.failures[0].stage is IngestionStage.VALIDATE
        assert "companyName" in summary.failures[0].reason
        assert await stored_titles(database) == [good["title"]]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_record_rejected_by_normalization_names_that_stage(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        good, other = page_body("page_one.json")["jobs"]
        empty_after_stripping = dict(other, description="<div><span></span></div>")

        summary = await ingest(database, ok(feed_page([good, empty_after_stripping])))

        assert summary.created == 1
        assert summary.failures[0].stage is IngestionStage.NORMALIZE
        assert summary.failures[0].source_job_id == other["guid"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unreachable_provider_still_reports_what_was_processed(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(
            database,
            ok(page_body("page_one.json")),
            *[httpx2.TimeoutException("read timed out")] * FAST_CONFIG.max_attempts,
        )

        assert summary.created == 2
        assert summary.failed == 1
        assert summary.failures[0].stage is IngestionStage.FETCH
        assert "timed out" in summary.failures[0].reason
        assert summary.processing_complete is False
        assert len(await stored_titles(database)) == 2

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_immediately_unreachable_provider_reports_an_empty_run(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(
            database, *[httpx2.ConnectError("refused")] * FAST_CONFIG.max_attempts
        )

        assert summary.fetched == 0
        assert summary.created == 0
        assert summary.failed == 1
        assert summary.failures[0].stage is IngestionStage.FETCH

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unusable_response_ends_the_run(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(database, httpx2.Response(503, text="down"))

        assert summary.fetched == 0
        assert summary.failures[0].stage is IngestionStage.FETCH
        assert "503" in summary.failures[0].reason

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_run_stops_at_its_record_budget(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(
            database,
            ok(page_body("page_one.json")),
            ok(page_body("page_two.json")),
            max_records=3,
        )

        assert summary.fetched == 3
        assert summary.created == 3
        assert summary.stopped_at_budget is True
        assert len(await stored_titles(database)) == 3

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_provenance_records_the_run_time(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        posting = page_body("page_one.json")["jobs"][0]
        await ingest(database, ok(feed_page([posting])))

        async with database.session() as session:
            provenance = (await session.scalars(select(JobProvenance))).one()

        assert provenance.first_seen_at == RUN_AT
        assert provenance.last_seen_at == RUN_AT
        assert provenance.raw_payload is not None
        assert provenance.raw_payload["guid"] == posting["guid"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_empty_feed_is_a_complete_run(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(database, ok(feed_page([])))

        assert summary.fetched == 0
        assert summary.processing_complete is True
        assert summary.reached_the_end is True
        assert summary.failures == ()

    run_database_test(database_url, exercise)


def test_a_run_must_have_a_record_budget() -> None:
    with pytest.raises(ValueError, match="max_records"):
        himalayas_run(FAST_CONFIG, max_records=0)


def test_the_run_registers_the_configured_source() -> None:
    run = himalayas_run(HimalayasConfig(base_url="https://example.test/api"))

    assert run.source.key == "himalayas"
    assert run.source.display_name == "Himalayas"
    assert run.source.base_url == "https://example.test/api"
    assert run.client.source_key == run.source.key


@pytest.mark.integration
def test_the_entry_point_runs_against_the_configured_database(database_url: PostgresDsn) -> None:
    """The scheduler entry point owns the engine and the client, so this
    exercises it end to end with only the outbound transport replaced."""

    async def exercise(database: Database) -> None:
        http_client = responding(ok(page_body("page_one.json")), ok(page_body("page_two.json")))
        try:
            summary = await ingest_himalayas(
                config=FAST_CONFIG,
                settings=Settings(database_url=PostgresDsn(str(database_url))),
                http_client=http_client,
            )
        finally:
            await http_client.aclose()

        assert summary.source_key == "himalayas"
        assert summary.created == 4
        assert summary.processing_complete is True
        assert len(await stored_titles(database)) == 4

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_entry_point_reports_an_unreachable_provider(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        http_client = responding(*[httpx2.ConnectError("refused")] * FAST_CONFIG.max_attempts)
        try:
            summary = await ingest_himalayas(
                config=FAST_CONFIG,
                settings=Settings(database_url=PostgresDsn(str(database_url))),
                http_client=http_client,
            )
        finally:
            await http_client.aclose()

        assert summary.fetched == 0
        assert summary.failures[0].stage is IngestionStage.FETCH

    run_database_test(database_url, exercise)
