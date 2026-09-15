"""A run that hits its licensed source's daily call quota mid-fetch."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

import pytest
from platform_db.models import Job
from pydantic import PostgresDsn
from sqlalchemy import select

from job_ingestion.contracts import RawPage, RawRecord
from job_ingestion.database import Database
from job_ingestion.errors import QuotaExceeded
from job_ingestion.persistence import SourceRegistration
from job_ingestion.pipeline import IngestionRun
from job_ingestion.schemas import NormalizedJob
from tests.support.catalog import with_empty_catalog

SOURCE_KEY = "fake-quota"
RUN_AT = datetime(2026, 9, 15, 12, tzinfo=UTC)


class FakeValidator:
    """Passes the raw record through untouched: validation is not under test."""

    def validate(self, record: RawRecord) -> RawRecord:
        return record


class FakeNormalizer:
    def normalize(self, record: RawRecord, raw: RawRecord) -> NormalizedJob:
        return NormalizedJob.model_validate(
            {
                "company": {"display_name": str(record["company"])},
                "title": str(record["title"]),
                "description": "A job.",
                "application_url": str(record["url"]),
                "provenance": {
                    "source_key": SOURCE_KEY,
                    "source_job_id": str(record["id"]),
                    "source_url": str(record["url"]),
                    "raw_payload": dict(raw),
                },
            }
        )


class QuotaLimitedClient:
    """Yields one page, then reports the source's daily call quota is spent.

    The quota is checked per call by `reserving_get` in real clients; this
    fake goes straight to the failure a real client would raise, because the
    pipeline's reaction to it -- not how a client discovers it -- is what this
    test exercises.
    """

    def __init__(self, records: tuple[RawRecord, ...], *, per_day: int = 1) -> None:
        self._records = records
        self._per_day = per_day
        self._reached_the_end = False

    @property
    def source_key(self) -> str:
        return SOURCE_KEY

    @property
    def reached_the_end(self) -> bool:
        return self._reached_the_end

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        yield RawPage(records=self._records)
        raise QuotaExceeded(SOURCE_KEY, self._per_day)


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


def make_run(client: QuotaLimitedClient) -> IngestionRun[RawRecord]:
    return IngestionRun(
        client=client,
        validator=FakeValidator(),
        normalizer=FakeNormalizer(),
        source=SourceRegistration(
            key=SOURCE_KEY,
            display_name="Fake Quota Source",
            base_url="https://fake-quota.example.test",
        ),
    )


@pytest.mark.integration
def test_a_run_stops_at_its_source_daily_call_quota(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        records = (
            {"id": "1", "title": "Engineer", "company": "Acme", "url": "https://example.test/1"},
            {"id": "2", "title": "Designer", "company": "Acme", "url": "https://example.test/2"},
        )
        run = make_run(QuotaLimitedClient(records))

        summary = await run.execute(database, clock=lambda: RUN_AT)

        assert summary.stopped_at_budget is True
        assert summary.fetched == len(records)
        assert summary.created == len(records)
        assert summary.failures == ()
        # The client never reached the end of the source: the quota, not the
        # source running out, is why this run stopped.
        assert summary.reached_the_end is False
        assert summary.source_exhausted is False

        async with database.session() as session:
            titles = sorted(await session.scalars(select(Job.title)))
        assert titles == ["Designer", "Engineer"]

    run_database_test(database_url, exercise)
