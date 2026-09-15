"""The Adzuna entry point end to end, with only the outbound transport replaced.

`require` installs the process-wide redaction filter and registers the key on
every configured run; `conftest` here undoes both after each test.
"""

import httpx2
import pytest
from platform_db.models import IngestionRun, IngestionRunState, JobProvenance
from pydantic import PostgresDsn
from sqlalchemy import select

from job_ingestion.adzuna.client import AdzunaClient, AdzunaConfig
from job_ingestion.adzuna.pipeline import build_run, ingest_adzuna
from job_ingestion.adzuna.source import DAILY_QUOTA
from job_ingestion.config import Settings
from job_ingestion.contracts import IngestionStage, IngestionSummary
from job_ingestion.database import Database
from job_ingestion.quota import Quota, reserve
from tests.adzuna.support import (
    APP_ID,
    APP_KEY,
    CREDENTIALS,
    never_opened,
    page_body,
    recording,
    run_database_test,
)
from tests.boards.fakes import ok
from tests.support.logs import capturing_logs

# One full page per country: two calls, six records, and neither country read
# to its end.
CONFIG = AdzunaConfig(
    countries=("gb", "de"), pages_per_country=1, results_per_page=3, retry_backoff_seconds=0.0
)


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLSYNC_ADZUNA_APP_ID", APP_ID)
    monkeypatch.setenv("SKILLSYNC_ADZUNA_APP_KEY", APP_KEY)


@pytest.fixture
def unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLSYNC_ADZUNA_APP_ID", APP_ID)
    monkeypatch.delenv("SKILLSYNC_ADZUNA_APP_KEY", raising=False)


async def ingest(
    database_url: PostgresDsn, *replies: httpx2.Response | Exception
) -> tuple[IngestionSummary, list[httpx2.Request]]:
    http_client, requests = recording(*replies)
    try:
        summary = await ingest_adzuna(
            config=CONFIG,
            settings=Settings(database_url=database_url),
            http_client=http_client,
        )
    finally:
        await http_client.aclose()
    return summary, requests


async def recorded_run(database: Database) -> IngestionRun:
    async with database.session() as session:
        return (
            await session.scalars(select(IngestionRun).where(IngestionRun.source_key == "adzuna"))
        ).one()


async def stored_payloads(database: Database) -> list[dict[str, object]]:
    async with database.session() as session:
        rows = await session.scalars(select(JobProvenance.raw_payload))
    return [payload for payload in rows if payload is not None]


async def spend(database: Database, calls: int) -> None:
    async with database.session() as session:
        assert await reserve(session, "adzuna", calls=calls, quota=Quota(per_day=calls))
        await session.commit()


@pytest.mark.integration
@pytest.mark.usefixtures("unconfigured")
def test_an_unconfigured_source_records_a_run_and_fetches_nothing(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        summary, requests = await ingest(database_url, ok(page_body("gb")))

        assert summary.source_key == "adzuna"
        assert summary.fetched == 0
        assert summary.failed == 1
        assert summary.failures[0].stage is IngestionStage.FETCH
        assert summary.failures[0].reason == "source unconfigured: SKILLSYNC_ADZUNA_APP_KEY"
        assert requests == []

        row = await recorded_run(database)
        assert row.state == IngestionRunState.COMPLETED
        assert row.failed == 1
        assert row.fetched == 0
        assert row.failure_summary is not None
        assert row.failure_summary["reasons"] == ["source unconfigured: SKILLSYNC_ADZUNA_APP_KEY"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
@pytest.mark.usefixtures("configured")
def test_a_configured_source_stores_every_snippet_flagged_partial(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        summary, requests = await ingest(database_url, ok(page_body("gb")), ok(page_body("de")))

        assert summary.fetched == 6
        assert summary.created == 6
        assert summary.failures == ()
        assert summary.processing_complete is True
        assert summary.reached_the_end is False
        assert summary.stopped_at_budget is False
        assert len(requests) == 2

        row = await recorded_run(database)
        assert row.state == IngestionRunState.COMPLETED
        assert row.created == 6

        payloads = await stored_payloads(database)
        assert len(payloads) == 6
        assert all(payload["_partial_description"] is True for payload in payloads)
        assert {payload["country"] for payload in payloads} == {"gb", "de"}

    run_database_test(database_url, exercise)


@pytest.mark.integration
@pytest.mark.usefixtures("configured")
def test_the_key_is_redacted_from_the_transports_own_request_line(
    database_url: PostgresDsn,
) -> None:
    """httpx2 logs every request line, query string included, at INFO. That
    line is the one place the key is written out by something other than
    this service, and `require` registers the key before the client exists
    precisely so it comes out redacted there."""

    async def exercise(database: Database) -> None:
        with capturing_logs("httpx2") as messages:
            await ingest(database_url, ok(page_body("gb")), ok(page_body("de")))

        request_lines = [message for message in messages if "HTTP Request" in message]
        assert len(request_lines) == 2
        assert all("app_key=[redacted]" in line for line in request_lines)
        assert APP_KEY not in "\n".join(messages)

    run_database_test(database_url, exercise)


@pytest.mark.integration
@pytest.mark.usefixtures("configured")
def test_a_spent_quota_stops_the_run_cleanly_before_any_request(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await spend(database, DAILY_QUOTA.per_day)

        summary, requests = await ingest(database_url, ok(page_body("gb")))

        assert summary.stopped_at_budget is True
        assert summary.fetched == 0
        assert summary.failures == ()
        assert summary.reached_the_end is False
        assert requests == []

        row = await recorded_run(database)
        assert row.state == IngestionRunState.COMPLETED
        assert row.stopped_at_budget is True
        assert row.failed == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
@pytest.mark.usefixtures("configured")
def test_a_quota_hit_mid_walk_keeps_what_was_already_fetched(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await spend(database, DAILY_QUOTA.per_day - 1)

        summary, requests = await ingest(database_url, ok(page_body("gb")), ok(page_body("de")))

        assert len(requests) == 1
        assert summary.fetched == 3
        assert summary.created == 3
        assert summary.stopped_at_budget is True
        assert summary.failures == ()

    run_database_test(database_url, exercise)


def test_the_run_registers_the_configured_source() -> None:
    client = AdzunaClient(
        AdzunaConfig(base_url="https://example.test/api"),
        CREDENTIALS,
        never_opened,  # type: ignore[arg-type]
    )

    run = build_run(client, 10)

    assert run.source.key == "adzuna"
    assert run.source.display_name == "Adzuna"
    assert run.source.base_url == "https://example.test/api"
    assert run.source.precedence == 10
    assert run.client.source_key == run.source.key
    assert run.max_records == 10
