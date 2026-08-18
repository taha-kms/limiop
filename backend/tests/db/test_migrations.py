import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import get_settings

BACKEND_ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_migrations_upgrade_and_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.getenv("SKILLSYNC_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("SKILLSYNC_TEST_DATABASE_URL is not configured")

    monkeypatch.setenv("SKILLSYNC_DATABASE_URL", database_url)
    get_settings.cache_clear()
    alembic_config = Config(BACKEND_ROOT / "alembic.ini")

    try:
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")
    finally:
        get_settings.cache_clear()
