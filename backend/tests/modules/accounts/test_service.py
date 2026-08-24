import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from pydantic import PostgresDsn

from app.db.session import Database
from app.modules.accounts.models import User
from app.modules.accounts.schemas import RegistrationRequest
from app.modules.accounts.service import EmailAlreadyRegistered, register

pytestmark = pytest.mark.integration


def run_database_test(
    database_url: PostgresDsn, test: Callable[[Database], Awaitable[None]]
) -> None:
    async def run() -> None:
        from sqlalchemy import delete

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


def test_a_concurrent_registration_of_the_same_address_is_rejected_not_500(
    database_url: PostgresDsn, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-check alone only catches an address that already has a
    committed row. A second registration that reaches its own commit before
    the first one lands still slips past that pre-check, and used to surface
    as an unhandled IntegrityError (a 500) instead of the same 409 a
    sequential duplicate gets. This simulates that window deterministically:
    a conflicting row is inserted through a second session in the gap
    between this session's pre-check SELECT and its own commit -- exactly
    where a real concurrent request would land."""

    async def test(database: Database) -> None:
        request = RegistrationRequest(email="ada@example.com", password="correct horse battery")
        async with database.session() as session:
            original_execute = session.execute

            async def racing_execute(statement: Any, *args: Any, **kwargs: Any) -> Any:
                result = await original_execute(statement, *args, **kwargs)
                async with database.session() as racer:
                    racer.add(User(email="ada@example.com", password_hash="x"))
                    await racer.commit()
                return result

            monkeypatch.setattr(session, "execute", racing_execute)

            with pytest.raises(EmailAlreadyRegistered):
                await register(session, request)

    run_database_test(database_url, test)
