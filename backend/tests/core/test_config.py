from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.core.config import Environment, Settings
from app.main import create_app


def test_settings_use_safe_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "SkillSync API"
    assert settings.environment is Environment.LOCAL
    assert settings.debug is False
    assert str(settings.database_url) == "postgresql+psycopg://localhost/skillsync"


def test_settings_load_prefixed_environment_variables(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLSYNC_APP_NAME", "Configured API")
    monkeypatch.setenv("SKILLSYNC_ENVIRONMENT", "staging")
    monkeypatch.setenv("SKILLSYNC_DEBUG", "true")
    monkeypatch.setenv(
        "SKILLSYNC_DATABASE_URL",
        "postgresql+psycopg://app@database.example/skillsync",
    )

    settings = Settings()

    assert settings.app_name == "Configured API"
    assert settings.environment is Environment.STAGING
    assert settings.debug is True
    assert str(settings.database_url) == "postgresql+psycopg://app@database.example/skillsync"


def test_settings_load_dotenv_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "SKILLSYNC_APP_NAME=Dotenv API\nSKILLSYNC_ENVIRONMENT=test\n",
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.app_name == "Dotenv API"
    assert settings.environment is Environment.TEST


def test_settings_reject_unknown_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLSYNC_ENVIRONMENT", "unknown")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_reject_non_postgresql_database_url(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLSYNC_DATABASE_URL", "sqlite:///skillsync.db")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_require_async_psycopg_driver(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLSYNC_DATABASE_URL", "postgresql://localhost/skillsync")

    with pytest.raises(ValidationError, match="postgresql\\+psycopg"):
        Settings()


def test_application_factory_uses_injected_settings() -> None:
    settings = Settings(app_name="Factory API", debug=True)

    application = create_app(settings)

    assert application.title == "Factory API"
    assert application.debug is True
    assert application.state.settings is settings
