import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest
from platform_db.models import Company, Job, JobProvenance, JobSource
from pydantic import PostgresDsn
from sqlalchemy import delete, select

from job_ingestion.arbeitnow.client import ArbeitnowConfig
from job_ingestion.arbeitnow.normalizer import ArbeitnowNormalizer
from job_ingestion.arbeitnow.pipeline import arbeitnow_run, ingest_arbeitnow
from job_ingestion.arbeitnow.records import ArbeitnowValidator
from job_ingestion.config import Settings
from job_ingestion.contracts import IngestionStage, IngestionSummary
from job_ingestion.database import Database
from job_ingestion.matching import match_key
from job_ingestion.pipeline import utc_now

FIXTURES = Path(__file__).parent / "fixtures"
FAST_CONFIG = ArbeitnowConfig(retry_backoff_seconds=0.0)
RUN_AT = datetime(2026, 8, 18, 12, tzinfo=UTC)


def board_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads((FIXTURES / "job_board_page.json").read_text())
    return body


def page(records: list[dict[str, Any]], *, has_next: bool = False) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "data": records,
            "links": {"next": "https://www.arbeitnow.com/api/job-board-api?page=2"}
            if has_next
            else {"next": None},
        },
    )


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
    config: ArbeitnowConfig = FAST_CONFIG,
    max_records: int = 100,
) -> IngestionSummary:
    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    run = arbeitnow_run(config, http_client=http_client, max_records=max_records)
    try:
        return await run.execute(database, clock=lambda: RUN_AT)
    finally:
        await http_client.aclose()


async def stored_titles(database: Database) -> list[str]:
    async with database.session() as session:
        return list(await session.scalars(select(Job.title).order_by(Job.title)))


@pytest.mark.integration
def test_a_full_board_page_reaches_postgresql(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(database, responding(page(board_body()["data"])))

        assert summary.source_key == "arbeitnow"
        assert summary.fetched == 2
        assert summary.created == 2
        assert summary.updated == 0
        assert summary.skipped == 0
        assert summary.failures == ()
        assert summary.processing_complete is True
        assert await stored_titles(database) == [
            "Senior Data Engineer",
            "Working Student Frontend",
        ]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_run_walks_every_page(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        first, second = board_body()["data"]
        summary = await ingest(
            database,
            responding(page([first], has_next=True), page([second])),
        )

        assert summary.fetched == 2
        assert summary.created == 2

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_running_twice_creates_nothing_new(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        records = board_body()["data"]
        first = await ingest(database, responding(page(records)))
        second = await ingest(database, responding(page(records)))

        assert first.created == 2
        assert second.created == 0
        assert second.skipped == 2
        assert second.processing_complete is True
        assert len(await stored_titles(database)) == 2

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_changed_posting_updates_rather_than_duplicates(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        records = board_body()["data"]
        await ingest(database, responding(page(records)))

        revised = [dict(records[0], description="<p>Now with Kafka.</p>"), records[1]]
        summary = await ingest(database, responding(page(revised)))

        assert summary.updated == 1
        assert summary.skipped == 1
        assert summary.created == 0
        assert len(await stored_titles(database)) == 2

        async with database.session() as session:
            descriptions = list(await session.scalars(select(Job.description)))

        assert "Now with Kafka." in descriptions

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_one_bad_record_does_not_hide_the_good_ones(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        good, other = board_body()["data"]
        broken = dict(other)
        del broken["company_name"]

        summary = await ingest(database, responding(page([good, broken])))

        assert summary.fetched == 2
        assert summary.created == 1
        assert summary.failed == 1
        assert summary.processing_complete is False
        assert summary.failures[0].stage is IngestionStage.VALIDATE
        assert "company_name" in summary.failures[0].reason
        assert await stored_titles(database) == ["Senior Data Engineer"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_record_rejected_by_normalization_names_that_stage(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        good, other = board_body()["data"]
        empty_after_stripping = dict(other, description="<div><span></span></div>")

        summary = await ingest(database, responding(page([good, empty_after_stripping])))

        assert summary.created == 1
        assert summary.failures[0].stage is IngestionStage.NORMALIZE
        assert summary.failures[0].source_job_id == "working-student-frontend-654321"

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unreachable_provider_still_reports_what_was_processed(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        records = board_body()["data"]
        summary = await ingest(
            database,
            responding(
                page(records, has_next=True),
                *[httpx2.TimeoutException("read timed out")] * FAST_CONFIG.max_attempts,
            ),
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
            database,
            responding(*[httpx2.ConnectError("refused")] * FAST_CONFIG.max_attempts),
        )

        assert summary.fetched == 0
        assert summary.created == 0
        assert summary.failed == 1
        assert summary.failures[0].stage is IngestionStage.FETCH

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
        records = board_body()["data"]
        summary = await ingest(database, responding(page(records)), max_records=1)

        assert summary.fetched == 1
        assert summary.created == 1
        assert len(await stored_titles(database)) == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_provenance_records_the_run_time(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, responding(page(board_body()["data"][:1])))

        async with database.session() as session:
            provenance = (await session.scalars(select(JobProvenance))).one()

        assert provenance.first_seen_at == RUN_AT
        assert provenance.last_seen_at == RUN_AT
        assert provenance.raw_payload is not None
        assert provenance.raw_payload["slug"] == "senior-data-engineer-berlin-123456"

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_empty_board_is_a_complete_run(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest(database, responding(page([])))

        assert summary.fetched == 0
        assert summary.processing_complete is True
        assert summary.failures == ()

    run_database_test(database_url, exercise)


def test_a_run_must_have_a_record_budget() -> None:
    with pytest.raises(ValueError, match="max_records"):
        arbeitnow_run(FAST_CONFIG, max_records=0)


def test_the_run_registers_the_configured_board() -> None:
    run = arbeitnow_run(ArbeitnowConfig(base_url="https://example.test/api"))

    assert run.source.key == "arbeitnow"
    assert run.source.display_name == "Arbeitnow"
    assert run.source.base_url == "https://example.test/api"
    assert run.client.source_key == run.source.key


def test_the_default_clock_reports_the_current_time_in_utc() -> None:
    before = datetime.now(UTC)
    stamped = utc_now()
    after = datetime.now(UTC)

    assert stamped.tzinfo is UTC
    assert before <= stamped <= after


@pytest.mark.integration
def test_a_record_persistence_refuses_is_reported_without_stopping_the_run(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        good, other = board_body()["data"]
        normalized = ArbeitnowNormalizer().normalize(ArbeitnowValidator().validate(other), other)
        value = match_key(normalized)

        # Two stored jobs already share the incoming record's canonical identity
        # and no provenance points at either, so persistence must refuse the
        # record rather than guess which one to update.
        async with database.session() as session:
            company = Company(display_name=normalized.company.display_name)
            for _index in range(2):
                session.add(
                    Job(
                        company=company,
                        match_key=value,
                        title=normalized.title,
                        location=normalized.location,
                        description=normalized.description,
                        application_url=str(normalized.application_url),
                    )
                )
            await session.commit()

        summary = await ingest(database, responding(page([good, other])))

        assert summary.fetched == 2
        assert summary.created == 1
        assert summary.skipped == 1
        assert summary.failed == 1
        assert summary.failures[0].stage is IngestionStage.PERSIST
        assert summary.failures[0].source_job_id == "working-student-frontend-654321"
        assert "2 stored jobs" in summary.failures[0].reason
        assert summary.processing_complete is False

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_entry_point_runs_against_the_configured_database(database_url: PostgresDsn) -> None:
    """The scheduler entry point owns the engine and the client, so this
    exercises it end to end with only the outbound transport replaced."""

    async def exercise(database: Database) -> None:
        http_client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(responding(page(board_body()["data"])))
        )
        try:
            summary = await ingest_arbeitnow(
                config=FAST_CONFIG,
                settings=Settings(database_url=PostgresDsn(str(database_url))),
                http_client=http_client,
            )
        finally:
            await http_client.aclose()

        assert summary.source_key == "arbeitnow"
        assert summary.created == 2
        assert summary.processing_complete is True
        assert len(await stored_titles(database)) == 2

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
            summary = await ingest_arbeitnow(
                config=FAST_CONFIG,
                settings=Settings(database_url=PostgresDsn(str(database_url))),
                http_client=http_client,
            )
        finally:
            await http_client.aclose()

        assert summary.fetched == 0
        assert summary.failures[0].stage is IngestionStage.FETCH

    run_database_test(database_url, exercise)


BLURB = "Acme is a public benefit corporation headquartered in San Francisco."


def posting(index: int) -> dict[str, Any]:
    """One employer's posting, carrying the blurb it puts on all of them."""
    record: dict[str, Any] = dict(board_body()["data"][0])
    record.update(
        {
            "slug": f"engineer-{index}",
            "title": f"Engineer {index}",
            "url": f"https://www.arbeitnow.com/jobs/companies/acme/engineer-{index}",
            "description": (
                f"<p>{BLURB}</p><p>Working fluency with data, including SQL.</p>"
                f"<p>Role {index}: build the pipelines that carry it.</p>"
            ),
        }
    )
    return record


async def stored_descriptions(database: Database) -> list[str]:
    async with database.session() as session:
        return list(await session.scalars(select(Job.description).order_by(Job.title)))


@pytest.mark.integration
def test_an_employers_blurb_is_gone_before_it_is_stored(database_url: PostgresDsn) -> None:
    """The candidate generator reads what is stored, so this is where it has to go."""

    async def exercise(database: Database) -> None:
        summary = await ingest(database, responding(page([posting(index) for index in range(5)])))

        assert summary.created == 5
        stored = await stored_descriptions(database)
        assert all(BLURB not in description for description in stored)
        assert all("including SQL" in description for description in stored)
        assert all(f"Role {index}" in stored[index] for index in range(5))

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_too_few_postings_to_establish_a_pattern_keep_the_blurb(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, responding(page([posting(index) for index in range(4)])))

        assert all(BLURB in description for description in await stored_descriptions(database))

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_small_run_is_stripped_when_the_catalogue_knows_the_employer(
    database_url: PostgresDsn,
) -> None:
    """Three postings are not a template; three of eight are.

    Arbeitnow delivers one employer a few postings at a time, so within a run
    they never reach the minimum. What establishes the pattern is the catalogue.
    """

    async def exercise(database: Database) -> None:
        await ingest(database, responding(page([posting(index) for index in range(5)])))

        await ingest(database, responding(page([posting(index) for index in range(5, 8)])))

        stored = await stored_descriptions(database)
        assert len(stored) == 8
        assert all(BLURB not in description for description in stored)
        assert all("including SQL" in description for description in stored)

    run_database_test(database_url, exercise)
