import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import PostgresDsn

from app.core.config import Environment, Settings, get_settings
from app.main import create_app

BACKEND_ROOT = Path(__file__).parents[1]

# Derived rather than listed. The hand-written list went stale the moment the
# session settings were added: nothing cleared SKILLSYNC_SESSION_SECRET, so on
# a machine where it was exported the suite both failed spuriously and signed
# its integration tokens with the operator's real key. Deriving it means a
# setting added tomorrow is isolated the day it lands.
SETTINGS_ENVIRONMENT_VARIABLES = tuple(
    f"SKILLSYNC_{field.upper()}" for field in Settings.model_fields
)


@pytest.fixture(autouse=True)
def isolate_settings_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for variable in SETTINGS_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_name="SkillSync Test API",
        environment=Environment.TEST,
        debug=False,
    )


@pytest.fixture
def application(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresDsn]:
    """A migrated PostgreSQL database, or a skip when none is configured."""
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


@pytest.fixture
def migrated_client(database_url: PostgresDsn) -> Iterator[TestClient]:
    """A client wired to a migrated database, with accounts cleared around it."""
    from sqlalchemy import create_engine, text

    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    settings = Settings(environment=Environment.TEST, database_url=database_url)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    engine.dispose()


@pytest.fixture
def production_like_client(database_url: PostgresDsn) -> Iterator[TestClient]:
    """Like `migrated_client`, but under `Environment.PRODUCTION` -- the only
    way to observe `Secure` on the session cookie, since it is off by design
    in local and test."""
    from sqlalchemy import create_engine, text

    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    settings = Settings(
        environment=Environment.PRODUCTION,
        session_secret="s" * 32,
        database_url=database_url,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    engine.dispose()
