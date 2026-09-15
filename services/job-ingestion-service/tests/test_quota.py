"""Reserving a licensed source's daily call budget, atomically."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date

import pytest
from platform_db.models import SourceQuotaUsage
from pydantic import PostgresDsn
from sqlalchemy import delete, select

from job_ingestion.database import Database
from job_ingestion.quota import Quota, reserve, used_today

SOURCE = "adzuna"
YESTERDAY = date(2026, 9, 14)
TODAY = date(2026, 9, 15)


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def clear(database: Database) -> None:
        async with database.session() as session:
            await session.execute(delete(SourceQuotaUsage))
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


async def stored_row(database: Database, *, day: date = TODAY) -> SourceQuotaUsage | None:
    async with database.session() as session:
        result = await session.scalars(
            select(SourceQuotaUsage).where(
                SourceQuotaUsage.source_key == SOURCE, SourceQuotaUsage.day == day
            )
        )
        return result.one_or_none()


async def calls_stored(database: Database, *, day: date = TODAY) -> int | None:
    row = await stored_row(database, day=day)
    return row.calls if row is not None else None


@pytest.mark.integration
def test_the_first_reservation_creates_the_row(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            reserved = await reserve(session, SOURCE, quota=Quota(per_day=10), today=TODAY)
            await session.commit()

        assert reserved is True
        assert await calls_stored(database) == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_reservations_up_to_the_budget_succeed_and_the_next_is_refused(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        quota = Quota(per_day=3)
        for _ in range(3):
            async with database.session() as session:
                reserved = await reserve(session, SOURCE, quota=quota, today=TODAY)
                await session.commit()
            assert reserved is True

        row_before = await stored_row(database)
        assert row_before is not None

        async with database.session() as session:
            refused = await reserve(session, SOURCE, quota=quota, today=TODAY)
            await session.commit()

        assert refused is False
        row_after = await stored_row(database)
        assert row_after is not None
        assert row_after.calls == 3
        # A refused reservation writes nothing, not even a touch: the row is
        # untouched down to its bookkeeping column.
        assert row_after.updated_at == row_before.updated_at

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_reservation_is_all_or_nothing(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        quota = Quota(per_day=3)

        async with database.session() as session:
            reserved = await reserve(session, SOURCE, calls=5, quota=quota, today=TODAY)
            await session.commit()

        assert reserved is False
        # Nothing was written: a fresh row is gated exactly like an existing one.
        assert await calls_stored(database) is None

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_reservation_against_an_existing_row_is_refused_when_it_would_overflow(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        quota = Quota(per_day=3)

        async with database.session() as session:
            assert await reserve(session, SOURCE, calls=2, quota=quota, today=TODAY) is True
            await session.commit()

        async with database.session() as session:
            refused = await reserve(session, SOURCE, calls=2, quota=quota, today=TODAY)
            await session.commit()

        assert refused is False
        assert await calls_stored(database) == 2

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_two_concurrent_reservations_against_a_budget_of_one_have_exactly_one_winner(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        quota = Quota(per_day=1)

        async def reserve_and_commit() -> bool:
            async with database.session() as session:
                reserved = await reserve(session, SOURCE, quota=quota, today=TODAY)
                await session.commit()
                return reserved

        results = await asyncio.gather(reserve_and_commit(), reserve_and_commit())

        assert sorted(results) == [False, True]
        assert await calls_stored(database) == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_used_today_reflects_the_stored_row(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            await reserve(session, SOURCE, calls=4, quota=Quota(per_day=10), today=TODAY)
            await session.commit()

        async with database.session() as session:
            assert await used_today(session, SOURCE, today=TODAY) == 4

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_new_day_starts_at_zero(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            await reserve(session, SOURCE, calls=4, quota=Quota(per_day=10), today=YESTERDAY)
            await session.commit()

        async with database.session() as session:
            assert await used_today(session, SOURCE, today=TODAY) == 0

    run_database_test(database_url, exercise)


def test_a_zero_daily_budget_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="per_day"):
        Quota(per_day=0)


@pytest.mark.integration
@pytest.mark.parametrize("calls", [0, -1])
def test_a_reservation_of_fewer_than_one_call_is_refused(
    database_url: PostgresDsn, calls: int
) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            with pytest.raises(ValueError, match="calls"):
                await reserve(session, SOURCE, calls=calls, quota=Quota(per_day=10), today=TODAY)
            await session.commit()

        # A rejected call never reaches the database: it cannot un-count calls
        # already spent, and it cannot slip past the check constraint either.
        assert await calls_stored(database) is None

    run_database_test(database_url, exercise)
