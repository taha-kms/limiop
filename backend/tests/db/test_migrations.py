import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import get_settings

BACKEND_ROOT = Path(__file__).parents[2]
PLATFORM_DB_ROOT = BACKEND_ROOT.parent / "platform" / "db"


@pytest.mark.integration
def test_migration_chains_upgrade_and_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.getenv("SKILLSYNC_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("SKILLSYNC_TEST_DATABASE_URL is not configured")

    monkeypatch.setenv("SKILLSYNC_DATABASE_URL", database_url)
    get_settings.cache_clear()
    backend_config = Config(BACKEND_ROOT / "alembic.ini")
    platform_config = Config(PLATFORM_DB_ROOT / "alembic.ini")

    try:
        command.downgrade(backend_config, "base")
        command.downgrade(platform_config, "base")
        command.upgrade(platform_config, "head")
        command.upgrade(backend_config, "head")
        command.downgrade(backend_config, "base")
        command.downgrade(platform_config, "base")
        command.upgrade(platform_config, "head")
        command.upgrade(backend_config, "head")
    finally:
        get_settings.cache_clear()
