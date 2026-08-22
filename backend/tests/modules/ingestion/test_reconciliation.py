import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from pydantic import PostgresDsn
from sqlalchemy import select

from app.db.session import Database
from app.modules.ingestion.contracts import (
    IngestionStage,
    IngestionSummary,
    RecordFailure,
)
from app.modules.ingestion.persistence import SourceRegistration, persist_job
from app.modules.ingestion.reconciliation import (
    expire_jobs_past_their_stated_date,
    reconcile,
    why_not,
    withdraw_jobs_nobody_lists,
)
from app.modules.jobs.domain import JobStatus
from app.modules.jobs.models import Job, JobProvenance
from app.modules.jobs.schemas import NormalizedJob
from tests.support.catalog import with_empty_catalog

BOARD = SourceRegistration(
    key="board", display_name="Board", base_url="https://board.example.com", precedence=20
)
AGGREGATOR = SourceRegistration(
    key="aggregator",
    display_name="Aggregator",
    base_url="https://aggregator.example.com",
    precedence=10,
)

FIRST_RUN = datetime(2026, 8, 1, 12, tzinfo=UTC)
SECOND_RUN = FIRST_RUN + timedelta(days=1)

TEXT = (
    "Build the pipelines the analytics team depends on, and own them end to end. "
    "You will work with engineers across the company."
)


def posting(source: SourceRegistration, **overrides: Any) -> NormalizedJob:
    payload: dict[str, Any] = {
        "company": {"display_name": "Acme GmbH"},
        "title": "Senior Data Engineer",
        "description": TEXT,
        "location": "Berlin",
        "application_url": "https://acme.example.com/jobs/1",
        "provenance": {
            "source_key": source.key,
            "source_job_id": f"{source.key}-1",
            "source_url": f"{source.base_url}/jobs/1",
        },
    }
    payload.update(overrides)
    return NormalizedJob.model_validate(payload)


def exhausted(source: SourceRegistration, **overrides: Any) -> IngestionSummary:
    """A run entitled to conclude that an unseen posting is gone."""
    fields: dict[str, Any] = {
        "source_key": source.key,
        "fetched": 1,
        "updated": 1,
        "reached_the_end": True,
        "stopped_at_budget": False,
    }
    fields.update(overrides)
    return IngestionSummary(**fields)


def run_database_test(database_url: PostgresDsn, test: Any) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


async def ingest(
    database: Database,
    source: SourceRegistration,
    incoming: NormalizedJob,
    *,
    seen_at: datetime,
) -> None:
    async with database.session() as session:
        await persist_job(session, incoming, source=source, seen_at=seen_at)
        await session.commit()


async def status_of(database: Database) -> JobStatus:
    async with database.session() as session:
        return (await session.scalars(select(Job))).one().status


async def run_reconcile(database: Database, summary: IngestionSummary, *, at: datetime) -> Any:
    async with database.session() as session:
        result = await reconcile(session, summary, run_started_at=at)
        await session.commit()
    return result


# A run that did not see everything cannot conclude that what it missed is gone.


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        pytest.param(
            IngestionSummary(
                source_key="board",
                fetched=5,
                created=5,
                reached_the_end=True,
                stopped_at_budget=True,
            ),
            "record budget",
            id="stopped at its budget",
        ),
        pytest.param(
            IngestionSummary(source_key="board", fetched=5, created=5, reached_the_end=False),
            "did not reach the end",
            id="never reached the end",
        ),
        pytest.param(
            IngestionSummary(
                source_key="board",
                fetched=5,
                created=4,
                reached_the_end=True,
                failures=(RecordFailure(stage=IngestionStage.FETCH, reason="a board was gone"),),
            ),
            "failure",
            id="a board was unreadable",
        ),
        pytest.param(
            IngestionSummary(
                source_key="board",
                fetched=5,
                created=4,
                reached_the_end=True,
                failures=(RecordFailure(stage=IngestionStage.VALIDATE, reason="bad record"),),
            ),
            "failure",
            id="one record failed",
        ),
        pytest.param(
            IngestionSummary(source_key="board", fetched=5, created=2, reached_the_end=True),
            "did not finish processing",
            id="records vanished without a failure",
        ),
    ],
)
def test_an_incomplete_run_may_not_conclude_anything(
    summary: IngestionSummary, expected: str
) -> None:
    assert summary.source_exhausted is False
    reason = why_not(summary)
    assert reason is not None
    assert expected in reason


def test_a_run_that_saw_everything_may_conclude() -> None:
    assert exhausted(BOARD).source_exhausted is True
    assert why_not(exhausted(BOARD)) is None


def test_processing_complete_does_not_imply_exhausted() -> None:
    """The distinction the whole rule rests on."""
    capped = IngestionSummary(
        source_key="board",
        fetched=120,
        created=120,
        reached_the_end=True,
        stopped_at_budget=True,
    )

    assert capped.processing_complete is True
    assert capped.source_exhausted is False


@pytest.mark.integration
@pytest.mark.parametrize(
    "summary",
    [
        pytest.param(
            IngestionSummary(
                source_key="board",
                fetched=1,
                created=1,
                reached_the_end=True,
                stopped_at_budget=True,
            ),
            id="capped",
        ),
        pytest.param(
            IngestionSummary(source_key="board", fetched=1, created=1, reached_the_end=False),
            id="truncated",
        ),
        pytest.param(
            IngestionSummary(
                source_key="board",
                fetched=1,
                created=1,
                reached_the_end=True,
                failures=(RecordFailure(stage=IngestionStage.FETCH, reason="gone"),),
            ),
            id="failed",
        ),
    ],
)
def test_an_incomplete_run_expires_nothing(
    database_url: PostgresDsn, summary: IngestionSummary
) -> None:
    """The property that matters most: a bad run must be unable to do harm."""

    async def exercise(database: Database) -> None:
        await ingest(database, BOARD, posting(BOARD), seen_at=FIRST_RUN)

        result = await run_reconcile(database, summary, at=SECOND_RUN)

        assert result.skipped is True
        assert result.reason
        assert result.provenance_retired == 0
        assert await status_of(database) is JobStatus.ACTIVE

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_posting_no_source_lists_any_more_is_withdrawn(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, BOARD, posting(BOARD), seen_at=FIRST_RUN)

        result = await run_reconcile(database, exhausted(BOARD), at=SECOND_RUN)

        assert result.ran is True
        assert result.provenance_retired == 1
        assert result.jobs_withdrawn == 1
        assert await status_of(database) is JobStatus.REMOVED

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_posting_this_run_saw_is_left_alone(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, BOARD, posting(BOARD), seen_at=SECOND_RUN)

        result = await run_reconcile(database, exhausted(BOARD), at=SECOND_RUN)

        assert result.provenance_retired == 0
        assert await status_of(database) is JobStatus.ACTIVE

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_posting_another_source_still_lists_stays_active(database_url: PostgresDsn) -> None:
    """One board dropping a posting says nothing about whether the job is open."""

    async def exercise(database: Database) -> None:
        await ingest(database, BOARD, posting(BOARD), seen_at=SECOND_RUN)
        await ingest(database, AGGREGATOR, posting(AGGREGATOR), seen_at=FIRST_RUN)

        result = await run_reconcile(database, exhausted(AGGREGATOR), at=SECOND_RUN)

        assert result.provenance_retired == 1
        assert result.jobs_withdrawn == 0
        assert await status_of(database) is JobStatus.ACTIVE

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_job_is_withdrawn_only_once_the_last_source_drops_it(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, BOARD, posting(BOARD), seen_at=FIRST_RUN)
        await ingest(database, AGGREGATOR, posting(AGGREGATOR), seen_at=FIRST_RUN)

        await run_reconcile(database, exhausted(AGGREGATOR), at=SECOND_RUN)
        assert await status_of(database) is JobStatus.ACTIVE

        await run_reconcile(database, exhausted(BOARD), at=SECOND_RUN)
        assert await status_of(database) is JobStatus.REMOVED

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_posting_that_comes_back_is_the_job_it_was(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, BOARD, posting(BOARD), seen_at=FIRST_RUN)
        await run_reconcile(database, exhausted(BOARD), at=SECOND_RUN)
        assert await status_of(database) is JobStatus.REMOVED

        later = SECOND_RUN + timedelta(days=1)
        await ingest(database, BOARD, posting(BOARD), seen_at=later)

        async with database.session() as session:
            jobs = (await session.scalars(select(Job))).all()
            provenance = (await session.scalars(select(JobProvenance))).all()

        assert len(jobs) == 1
        assert jobs[0].status is JobStatus.ACTIVE
        assert provenance[0].retired_at is None

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_reconciling_twice_withdraws_nothing_the_second_time(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, BOARD, posting(BOARD), seen_at=FIRST_RUN)

        first = await run_reconcile(database, exhausted(BOARD), at=SECOND_RUN)
        second = await run_reconcile(database, exhausted(BOARD), at=SECOND_RUN)

        assert first.jobs_withdrawn == 1
        assert second.provenance_retired == 0
        assert second.jobs_withdrawn == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_source_that_never_wrote_anything_reconciles_to_nothing(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        result = await run_reconcile(database, exhausted(BOARD), at=SECOND_RUN)

        assert result.ran is True
        assert result.provenance_retired == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_one_source_reconciling_does_not_retire_another_sources_records(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, BOARD, posting(BOARD), seen_at=FIRST_RUN)
        await ingest(database, AGGREGATOR, posting(AGGREGATOR), seen_at=FIRST_RUN)

        await run_reconcile(database, exhausted(AGGREGATOR), at=SECOND_RUN)

        async with database.session() as session:
            records = {
                record.source_job_id: record.retired_at
                for record in (await session.scalars(select(JobProvenance))).all()
            }

        assert records["aggregator-1"] is not None
        assert records["board-1"] is None

    run_database_test(database_url, exercise)


# Expiry is a stated fact rather than an inference, so it needs no exhausted run.


@pytest.mark.integration
def test_a_job_past_its_stated_date_expires(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await ingest(
            database,
            BOARD,
            posting(BOARD, published_at=FIRST_RUN, expires_at=SECOND_RUN),
            seen_at=FIRST_RUN,
        )

        async with database.session() as session:
            expired = await expire_jobs_past_their_stated_date(
                session, now=SECOND_RUN + timedelta(days=1)
            )
            await session.commit()

        assert expired == 1
        assert await status_of(database) is JobStatus.EXPIRED

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_job_before_its_stated_date_is_left_alone(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await ingest(
            database,
            BOARD,
            posting(BOARD, published_at=FIRST_RUN, expires_at=SECOND_RUN),
            seen_at=FIRST_RUN,
        )

        async with database.session() as session:
            expired = await expire_jobs_past_their_stated_date(session, now=FIRST_RUN)
            await session.commit()

        assert expired == 0
        assert await status_of(database) is JobStatus.ACTIVE

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_job_that_stated_no_date_never_expires_on_its_own(
    database_url: PostgresDsn,
) -> None:
    """Every source examined leaves the field empty, so this is the ordinary case."""

    async def exercise(database: Database) -> None:
        await ingest(database, BOARD, posting(BOARD), seen_at=FIRST_RUN)

        async with database.session() as session:
            expired = await expire_jobs_past_their_stated_date(
                session, now=SECOND_RUN + timedelta(days=3650)
            )
            await session.commit()

        assert expired == 0
        assert await status_of(database) is JobStatus.ACTIVE

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_several_postings_disappearing_at_once_are_all_withdrawn(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        for number in (1, 2, 3):
            await ingest(
                database,
                BOARD,
                posting(
                    BOARD,
                    title=f"Senior Data Engineer {number}",
                    provenance={
                        "source_key": BOARD.key,
                        "source_job_id": f"board-{number}",
                        "source_url": f"{BOARD.base_url}/jobs/{number}",
                    },
                ),
                seen_at=FIRST_RUN,
            )

        result = await run_reconcile(database, exhausted(BOARD), at=SECOND_RUN)

        async with database.session() as session:
            statuses = {job.status for job in (await session.scalars(select(Job))).all()}

        assert result.provenance_retired == 3
        assert result.jobs_withdrawn == 3
        assert statuses == {JobStatus.REMOVED}

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_job_one_source_listed_twice_is_withdrawn_once(database_url: PostgresDsn) -> None:
    """A board can advertise one posting under two identifiers."""

    async def exercise(database: Database) -> None:
        await ingest(database, BOARD, posting(BOARD), seen_at=FIRST_RUN)
        await ingest(
            database,
            BOARD,
            posting(
                BOARD,
                provenance={
                    "source_key": BOARD.key,
                    "source_job_id": "board-duplicate",
                    "source_url": f"{BOARD.base_url}/jobs/1b",
                },
            ),
            seen_at=FIRST_RUN,
        )

        async with database.session() as session:
            assert len((await session.scalars(select(Job))).all()) == 1
            assert len((await session.scalars(select(JobProvenance))).all()) == 2

        result = await run_reconcile(database, exhausted(BOARD), at=SECOND_RUN)

        assert result.provenance_retired == 2
        assert result.jobs_withdrawn == 1
        assert await status_of(database) is JobStatus.REMOVED

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_withdrawing_an_identifier_naming_no_job_changes_nothing(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            withdrawn = await withdraw_jobs_nobody_lists(session, {uuid4()})
            await session.commit()

        assert withdrawn == 0

    run_database_test(database_url, exercise)
