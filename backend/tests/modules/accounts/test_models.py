import asyncio
from collections.abc import Awaitable, Callable

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.db.session import Database
from app.modules.accounts.models import User, normalize_email

pytestmark = pytest.mark.integration


def run_database_test(
    database_url: PostgresDsn, test: Callable[[Database], Awaitable[None]]
) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                await session.execute(delete(User))
                await session.commit()
            await test(database)
        finally:
            async with database.session() as session:
                await session.execute(delete(User))
                await session.commit()
            await database.dispose()

    asyncio.run(run())


def test_normalize_email_lowercases_and_trims() -> None:
    assert normalize_email("  Ada@Example.COM ") == "ada@example.com"


def test_the_same_address_cannot_register_twice(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        async with database.session() as session:
            session.add(User(email="Ada@Example.com", password_hash="x"))
            await session.commit()
        with pytest.raises(IntegrityError):
            async with database.session() as session:
                session.add(User(email="ada@example.COM", password_hash="y"))
                await session.commit()

    run_database_test(database_url, test)


def test_a_bulk_update_that_desyncs_normalization_is_rejected(database_url: PostgresDsn) -> None:
    # A Core-level statement bypasses the `@validates` hook entirely, so this
    # proves the guarantee holds at the database layer, not just in the ORM.
    async def test(database: Database) -> None:
        async with database.session() as session:
            session.add(User(email="ada@example.com", password_hash="x"))
            await session.commit()
        with pytest.raises(IntegrityError):
            async with database.session() as session:
                await session.execute(update(User).values(email="changed@example.com"))
                await session.commit()

    run_database_test(database_url, test)


def test_an_address_with_a_tab_is_normalized_not_rejected(database_url: PostgresDsn) -> None:
    # `str.strip()` (used by `normalize_email()`) trims tabs; a bare `btrim`
    # trims only spaces. The database constraint's trim set must match, or a
    # value Python considers already-normalized is rejected as a false
    # desync.
    async def test(database: Database) -> None:
        async with database.session() as session:
            session.add(User(email="\tada@example.com\t", password_hash="x"))
            await session.commit()
        async with database.session() as session:
            user = (await session.execute(select(User))).scalars().one()
            assert user.normalized_email == "ada@example.com"

    run_database_test(database_url, test)


def test_a_new_account_starts_active_at_version_one(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        async with database.session() as session:
            session.add(User(email="grace@example.com", password_hash="x"))
            await session.commit()
        async with database.session() as session:
            user = (await session.execute(select(User))).scalars().one()
            assert user.is_active is True
            assert user.token_version == 1
            assert user.normalized_email == "grace@example.com"

    run_database_test(database_url, test)
