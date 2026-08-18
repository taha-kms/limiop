import asyncio
import os
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_database_session
from app.core.config import Environment, Settings
from app.main import create_app

pytestmark = pytest.mark.integration


def test_database_session_uses_postgresql() -> None:
    database_url = os.getenv("SKILLSYNC_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("SKILLSYNC_TEST_DATABASE_URL is not configured")

    application = create_app(
        Settings(
            environment=Environment.TEST,
            database_url=PostgresDsn(database_url),
        )
    )

    @application.get("/test/database")
    async def database_check(
        session: Annotated[AsyncSession, Depends(get_database_session)],
    ) -> dict[str, int]:
        value = await session.scalar(text("SELECT 1"))
        return {"value": value}

    with TestClient(application) as client:
        response = client.get("/test/database")

    assert response.status_code == 200
    assert response.json() == {"value": 1}


def test_database_session_rolls_back_on_error() -> None:
    database_url = os.getenv("SKILLSYNC_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("SKILLSYNC_TEST_DATABASE_URL is not configured")

    async def exercise_rollback() -> None:
        from app.db.session import Database

        database = Database(PostgresDsn(database_url))
        try:
            with pytest.raises(RuntimeError, match="rollback"):
                async with database.session() as session:
                    await session.execute(
                        text("CREATE TEMPORARY TABLE rollback_probe (value integer)")
                    )
                    raise RuntimeError("rollback")
        finally:
            await database.dispose()

    asyncio.run(exercise_rollback())
