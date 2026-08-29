import asyncio
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import PostgresDsn

from app.core.config import Environment, Settings
from app.db.session import Database
from app.main import create_app
from tests.support.catalog import clear, seed
from tests.support.ingestion import clear_runs, seed_runs


@pytest.fixture
def catalog_client(database_url: PostgresDsn) -> Iterator[TestClient]:
    """A client wired to the test database, over a catalog and history that start empty."""
    application = create_app(
        Settings(
            app_name="SkillSync Test API",
            environment=Environment.TEST,
            debug=False,
            database_url=database_url,
        )
    )

    async def empty() -> None:
        database = Database(database_url)
        try:
            await clear(database)
            await clear_runs(database)
        finally:
            await database.dispose()

    asyncio.run(empty())
    try:
        with TestClient(application) as client:
            yield client
    finally:
        asyncio.run(empty())


@pytest.fixture
def seed_catalog(database_url: PostgresDsn) -> Callable[..., dict[str, Any]]:
    """Insert jobs from a synchronous test, returning their ids by title."""

    def insert(*specs: dict[str, Any]) -> dict[str, Any]:
        async def run() -> dict[str, Any]:
            database = Database(database_url)
            try:
                return dict(await seed(database, *specs))
            finally:
                await database.dispose()

        return asyncio.run(run())

    return insert


@pytest.fixture
def seed_ingestion_runs(database_url: PostgresDsn) -> Callable[..., None]:
    """Insert ingestion runs from a synchronous test."""

    def insert(*specs: dict[str, Any]) -> None:
        async def run() -> None:
            database = Database(database_url)
            try:
                await seed_runs(database, *specs)
            finally:
                await database.dispose()

        asyncio.run(run())

    return insert
