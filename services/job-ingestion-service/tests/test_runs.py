"""Recording what one ingestion execution did."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import pytest
from platform_db.models import IngestionRun, IngestionRunState
from pydantic import PostgresDsn
from sqlalchemy import delete, select

from job_ingestion.contracts import IngestionStage, IngestionSummary, RecordFailure
from job_ingestion.database import Database
from job_ingestion.runs import complete_run, failure_summary, recorded_run

SOURCE = "arbeitnow"


def test_a_clean_run_summarises_no_failures() -> None:
    assert failure_summary(()) is None


def test_failures_are_counted_by_stage_and_sampled() -> None:
    failures = (
        *(
            RecordFailure(stage=IngestionStage.VALIDATE, reason=f"reason {index}")
            for index in range(8)
        ),
        RecordFailure(stage=IngestionStage.PERSIST, reason="a write failed"),
    )

    summary = failure_summary(failures)

    assert summary is not None
    assert summary["total"] == 9
    assert summary["by_stage"] == {"validate": 8, "persist": 1}
    # Enough to see the shape of a bad run, not enough to become a log.
    assert len(summary["reasons"]) == 5  # type: ignore[arg-type]


def test_the_same_reason_many_times_is_sampled_once() -> None:
    failures = tuple(
        RecordFailure(stage=IngestionStage.VALIDATE, reason="the same problem") for _ in range(20)
    )

    summary = failure_summary(failures)

    assert summary is not None
    assert summary["total"] == 20
    assert summary["reasons"] == ["the same problem"]


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def clear(database: Database) -> None:
        async with database.session() as session:
            await session.execute(delete(IngestionRun))
            await session.commit()

    async def go() -> None:
        database = Database(database_url)
        try:
            await clear(database)
            await test(database)
        finally:
            await clear(database)
            await database.dispose()

    asyncio.run(go())


async def stored(database: Database) -> IngestionRun:
    async with database.session() as session:
        return (await session.scalars(select(IngestionRun))).one()


def summary(**overrides: object) -> IngestionSummary:
    return IngestionSummary(source_key=SOURCE, **overrides)  # type: ignore[arg-type]


@pytest.mark.integration
def test_a_run_is_recorded_while_it_is_still_running(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        async with recorded_run(database, SOURCE):
            row = await stored(database)
            assert row.state == IngestionRunState.RUNNING
            assert row.finished_at is None
            assert row.source_key == SOURCE

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_finished_run_records_what_it_did(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        async with recorded_run(database, SOURCE) as run_id:
            pass
        await complete_run(
            database,
            run_id,
            summary(
                fetched=10,
                created=6,
                updated=3,
                skipped=1,
                reached_the_end=True,
                alias_version="2026.08.29.1",
                mentions_resolved=42,
            ),
        )

        row = await stored(database)
        assert row.state == IngestionRunState.COMPLETED
        assert row.finished_at is not None
        assert (row.fetched, row.created, row.updated, row.skipped) == (10, 6, 3, 1)
        assert row.reached_the_end is True
        assert row.alias_version == "2026.08.29.1"
        assert row.mentions_resolved == 42

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_run_that_handled_a_bad_record_still_completed(database_url: PostgresDsn) -> None:
    """Record failures are not run failures.

    A run that rejected one posting and carried on did its job. The counts say
    how much of it was clean, and `source_exhausted` already refuses the
    conclusions a failure should deny.
    """

    async def test(database: Database) -> None:
        async with recorded_run(database, SOURCE) as run_id:
            pass
        await complete_run(
            database,
            run_id,
            summary(
                fetched=2,
                created=1,
                failures=(RecordFailure(stage=IngestionStage.VALIDATE, reason="no title"),),
            ),
        )

        row = await stored(database)
        assert row.state == IngestionRunState.COMPLETED
        assert row.failed == 1
        assert row.failure_summary == {
            "total": 1,
            "by_stage": {"validate": 1},
            "reasons": ["no title"],
        }

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_run_that_raised_is_recorded_as_failed_and_the_error_continues(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        with pytest.raises(RuntimeError):
            async with recorded_run(database, SOURCE):
                raise RuntimeError("https://provider.example.com/?api_key=secret failed")

        row = await stored(database)
        assert row.state == IngestionRunState.FAILED
        assert row.finished_at is not None
        # The class name, not the message: a provider's error text can carry a
        # URL with a key in it, and this column is read by people.
        assert row.failure_summary == {"total": 1, "by_stage": {}, "reasons": ["RuntimeError"]}

    run_database_test(database_url, test)


@pytest.mark.integration
def test_bookkeeping_that_cannot_be_written_does_not_end_the_run(
    database_url: PostgresDsn,
) -> None:
    """A pipeline stopped by its own bookkeeping is worse than missing rows.

    The database itself is made unreachable rather than the writer stubbed out,
    because the writer is what does the swallowing and replacing it would test
    the opposite of the guarantee.
    """

    async def test(_: Database) -> None:
        unreachable = Database(
            PostgresDsn("postgresql+psycopg://nobody:nobody@127.0.0.1:1/nothing")
        )
        try:
            async with recorded_run(unreachable, SOURCE) as run_id:
                assert isinstance(run_id, UUID)
            await complete_run(unreachable, run_id, summary())
        finally:
            await unreachable.dispose()

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_run_cannot_be_terminal_without_a_finish_time(database_url: PostgresDsn) -> None:
    """Asserted by the database, because a half-written row outlives the code."""
    from sqlalchemy.exc import IntegrityError

    async def test(database: Database) -> None:
        async with database.session() as session:
            session.add(
                IngestionRun(
                    source_key=SOURCE,
                    state=IngestionRunState.COMPLETED,
                    started_at=datetime.now(UTC),
                    finished_at=None,
                    fetched=0,
                    created=0,
                    updated=0,
                    skipped=0,
                    failed=0,
                    reached_the_end=False,
                    stopped_at_budget=False,
                    mentions_resolved=0,
                    mentions_unknown=0,
                    extraction_failed=0,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    run_database_test(database_url, test)
