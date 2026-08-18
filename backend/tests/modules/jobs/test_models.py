import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pydantic import PostgresDsn
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import Database
from app.modules.jobs.models import JobSource

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).parents[3]


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresDsn]:
    value = os.getenv("SKILLSYNC_TEST_DATABASE_URL")
    if value is None:
        pytest.skip("SKILLSYNC_TEST_DATABASE_URL is not configured")

    monkeypatch.setenv("SKILLSYNC_DATABASE_URL", value)
    get_settings.cache_clear()
    command.upgrade(Config(BACKEND_ROOT / "alembic.ini"), "head")

    try:
        yield PostgresDsn(value)
    finally:
        get_settings.cache_clear()


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                await session.execute(delete(JobSource))
                await session.commit()
            await test(database)
        finally:
            async with database.session() as session:
                await session.execute(delete(JobSource))
                await session.commit()
            await database.dispose()

    asyncio.run(run())


def test_job_source_uses_shared_metadata() -> None:
    assert JobSource.metadata is Base.metadata


def test_job_source_round_trip(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        source = JobSource(
            key="arbeitnow",
            display_name="Arbeitnow",
            base_url="https://www.arbeitnow.com",
        )

        async with database.session() as session:
            session.add(source)
            await session.commit()
            source_id = source.id

        async with database.session() as session:
            stored = await session.scalar(select(JobSource).where(JobSource.id == source_id))

        assert stored is not None
        assert isinstance(stored.id, UUID)
        assert stored.key == "arbeitnow"
        assert stored.display_name == "Arbeitnow"
        assert stored.base_url == "https://www.arbeitnow.com"
        assert stored.created_at.tzinfo is not None
        assert stored.updated_at.tzinfo is not None

    run_database_test(database_url, exercise)


def test_job_source_key_must_be_unique(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            session.add_all(
                [
                    JobSource(
                        key="arbeitnow",
                        display_name="Arbeitnow",
                        base_url="https://www.arbeitnow.com",
                    ),
                    JobSource(
                        key="arbeitnow",
                        display_name="Duplicate Arbeitnow",
                        base_url="https://example.com",
                    ),
                ]
            )

            with pytest.raises(IntegrityError):
                await session.commit()

    run_database_test(database_url, exercise)
