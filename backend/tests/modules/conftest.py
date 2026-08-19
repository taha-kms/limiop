import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import PostgresDsn

from app.core.config import get_settings

BACKEND_ROOT = Path(__file__).parents[2]


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
