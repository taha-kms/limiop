import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from platform_db.models import Company
from platform_db.models.boards import BoardStatus, JobBoard
from pydantic import PostgresDsn
from sqlalchemy import select

from job_ingestion.boards.client import BoardOutcome
from job_ingestion.boards.lifecycle import (
    INACTIVE_AFTER_FAILURES,
    LifecycleResult,
    reactivate,
    record_poll,
)
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration, ensure_source
from tests.boards.fakes import FAKE_BASE_URL
from tests.support.catalog import with_empty_catalog


def run_database_test(database_url: PostgresDsn, test: Any) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


async def register(database: Database, slug: str, **fields: Any) -> None:
    fields.setdefault("status", BoardStatus.CONFIRMED)
    async with database.session() as session:
        source = await ensure_source(
            session,
            SourceRegistration(key="fake", display_name="Fake Boards", base_url=FAKE_BASE_URL),
        )
        session.add(JobBoard(source_id=source.id, slug=slug, **fields))
        await session.commit()


async def board_row(database: Database, slug: str) -> JobBoard:
    async with database.session() as session:
        return (await session.scalars(select(JobBoard).where(JobBoard.slug == slug))).one()


@pytest.mark.integration
def test_a_success_resets_the_streak_and_records_the_count(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await register(database, "acme", consecutive_failures=2)
        polled_at = datetime.now(UTC)

        async with database.session() as session:
            result = await record_poll(
                session,
                source_key="fake",
                outcomes=[BoardOutcome("acme", 5, None)],
                polled_at=polled_at,
            )
            await session.commit()

        assert result == LifecycleResult(polled=1, retired=())

        row = await board_row(database, "acme")
        assert row.last_posting_count == 5
        assert row.consecutive_failures == 0
        assert row.last_polled_at == polled_at

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_failure_increments_the_streak(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await register(database, "acme")

        async with database.session() as session:
            await record_poll(
                session,
                source_key="fake",
                outcomes=[BoardOutcome("acme", None, "board acme returned status 404")],
                polled_at=datetime.now(UTC),
            )
            await session.commit()

        row = await board_row(database, "acme")
        assert row.consecutive_failures == 1
        assert row.status is BoardStatus.CONFIRMED

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_third_consecutive_failure_retires_the_board(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await register(database, "acme")

        async def fail() -> Any:
            async with database.session() as session:
                result = await record_poll(
                    session,
                    source_key="fake",
                    outcomes=[BoardOutcome("acme", None, "board acme returned status 404")],
                    polled_at=datetime.now(UTC),
                )
                await session.commit()
                return result

        for _ in range(INACTIVE_AFTER_FAILURES - 1):
            result = await fail()
            assert result.retired == ()

        result = await fail()

        assert result.retired == ("acme",)
        row = await board_row(database, "acme")
        assert row.status is BoardStatus.INACTIVE
        assert row.consecutive_failures == INACTIVE_AFTER_FAILURES

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_failure_against_an_already_inactive_row_is_not_reported_as_retired_again(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await register(
            database,
            "acme",
            status=BoardStatus.INACTIVE,
            consecutive_failures=INACTIVE_AFTER_FAILURES,
        )

        async with database.session() as session:
            result = await record_poll(
                session,
                source_key="fake",
                outcomes=[BoardOutcome("acme", None, "board acme returned status 404")],
                polled_at=datetime.now(UTC),
            )
            await session.commit()

        assert result.retired == ()
        row = await board_row(database, "acme")
        assert row.status is BoardStatus.INACTIVE
        assert row.consecutive_failures == INACTIVE_AFTER_FAILURES + 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_success_against_an_inactive_row_with_provider_evidence_reactivates_it(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            company = Company(display_name="Acme")
            session.add(company)
            await session.commit()
            company_id = company.id

        await register(
            database,
            "acme",
            status=BoardStatus.INACTIVE,
            consecutive_failures=INACTIVE_AFTER_FAILURES,
            company_id=company_id,
            evidence={"kind": "provider_name"},
        )

        async with database.session() as session:
            result = await record_poll(
                session,
                source_key="fake",
                outcomes=[BoardOutcome("acme", 3, None)],
                polled_at=datetime.now(UTC),
            )
            await session.commit()

        assert result.reactivated == ("acme",)
        row = await board_row(database, "acme")
        assert row.status is BoardStatus.CONFIRMED
        assert row.consecutive_failures == 0
        assert row.last_posting_count == 3

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_pinned_row_reaches_the_threshold_and_stays_confirmed(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await register(database, "acme", pinned=True)

        async with database.session() as session:
            for _ in range(INACTIVE_AFTER_FAILURES):
                result = await record_poll(
                    session,
                    source_key="fake",
                    outcomes=[BoardOutcome("acme", None, "board acme returned status 404")],
                    polled_at=datetime.now(UTC),
                )
            await session.commit()

        assert result.retired == ()
        row = await board_row(database, "acme")
        assert row.status is BoardStatus.CONFIRMED
        assert row.consecutive_failures == INACTIVE_AFTER_FAILURES

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_slug_without_a_row_is_skipped(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            await ensure_source(
                session,
                SourceRegistration(key="fake", display_name="Fake Boards", base_url=FAKE_BASE_URL),
            )
            await session.commit()

        async with database.session() as session:
            result = await record_poll(
                session,
                source_key="fake",
                outcomes=[BoardOutcome("ghost", 1, None)],
                polled_at=datetime.now(UTC),
            )
            await session.commit()

        assert result == LifecycleResult(polled=0, retired=())

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_reactivate_on_an_inactive_discovered_row_with_a_company_confirms_it(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            company = Company(display_name="Acme")
            session.add(company)
            await session.commit()
            company_id = company.id

        await register(
            database,
            "acme",
            status=BoardStatus.INACTIVE,
            consecutive_failures=INACTIVE_AFTER_FAILURES,
            company_id=company_id,
            evidence={"kind": "provider_name"},
        )

        async with database.session() as session:
            changed = await reactivate(session, source_key="fake", slug="acme")
            await session.commit()

        assert changed is True
        row = await board_row(database, "acme")
        assert row.status is BoardStatus.CONFIRMED
        assert row.consecutive_failures == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_reactivate_on_an_inactive_row_without_a_company_returns_it_to_candidate(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await register(
            database,
            "acme",
            status=BoardStatus.INACTIVE,
            consecutive_failures=INACTIVE_AFTER_FAILURES,
        )

        async with database.session() as session:
            changed = await reactivate(session, source_key="fake", slug="acme")
            await session.commit()

        assert changed is True
        row = await board_row(database, "acme")
        assert row.status is BoardStatus.CANDIDATE
        assert row.consecutive_failures == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_reactivate_on_an_inactive_operator_pinned_row_that_lost_its_pin_goes_to_candidate(
    database_url: PostgresDsn,
) -> None:
    """An operator's own evidence does not name a company, so it does not
    stand in for verification once the pin protecting the row is gone."""

    async def exercise(database: Database) -> None:
        async with database.session() as session:
            company = Company(display_name="Acme")
            session.add(company)
            await session.commit()
            company_id = company.id

        await register(
            database,
            "acme",
            status=BoardStatus.INACTIVE,
            consecutive_failures=INACTIVE_AFTER_FAILURES,
            company_id=company_id,
            evidence={"kind": "operator", "checked_at": "2026-01-01T00:00:00+00:00"},
            pinned=False,
        )

        async with database.session() as session:
            changed = await reactivate(session, source_key="fake", slug="acme")
            await session.commit()

        assert changed is True
        row = await board_row(database, "acme")
        assert row.status is BoardStatus.CANDIDATE
        assert row.consecutive_failures == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_reactivate_on_a_non_inactive_row_does_nothing(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await register(database, "acme")

        async with database.session() as session:
            changed = await reactivate(session, source_key="fake", slug="acme")

        assert changed is False
        row = await board_row(database, "acme")
        assert row.status is BoardStatus.CONFIRMED

    run_database_test(database_url, exercise)
