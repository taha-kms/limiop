import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import PostgresDsn

REPOSITORY_ROOT = Path(__file__).parents[3]
PLATFORM_DB_ROOT = REPOSITORY_ROOT / "platform" / "db"


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresDsn]:
    """A migrated PostgreSQL database, or a skip when none is configured."""
    value = os.getenv("SKILLSYNC_TEST_DATABASE_URL")
    if value is None:
        pytest.skip("SKILLSYNC_TEST_DATABASE_URL is not configured")

    monkeypatch.setenv("SKILLSYNC_DATABASE_URL", value)
    command.upgrade(Config(PLATFORM_DB_ROOT / "alembic.ini"), "head")
    yield PostgresDsn(value)
