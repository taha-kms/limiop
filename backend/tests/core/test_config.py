from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.core.config import (
    DEVELOPMENT_SESSION_SECRET,
    MIN_SESSION_SECRET_LENGTH,
    Environment,
    Settings,
)
from app.main import create_app
from app.modules.cvs.policy import DEFAULT_CV_MAX_UPLOAD_BYTES, CVFormat


def test_settings_use_safe_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "SkillSync API"
    assert settings.environment is Environment.LOCAL
    assert settings.debug is False
    assert str(settings.database_url) == "postgresql+psycopg://localhost/skillsync"
    assert settings.cv_max_upload_bytes == DEFAULT_CV_MAX_UPLOAD_BYTES
    assert settings.cv_allowed_formats == (CVFormat.PDF,)
    assert settings.cv_storage_root == Path("uploads/cvs")
    assert settings.cv_pdf_max_pages == 20
    assert settings.cv_pdf_max_text_characters == 100_000
    assert settings.cv_pdf_timeout_seconds == 5.0


def test_settings_load_prefixed_environment_variables(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLSYNC_APP_NAME", "Configured API")
    monkeypatch.setenv("SKILLSYNC_ENVIRONMENT", "staging")
    monkeypatch.setenv("SKILLSYNC_DEBUG", "true")
    monkeypatch.setenv(
        "SKILLSYNC_DATABASE_URL",
        "postgresql+psycopg://app@database.example/skillsync",
    )
    monkeypatch.setenv("SKILLSYNC_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("SKILLSYNC_CV_MAX_UPLOAD_BYTES", "1048576")
    monkeypatch.setenv("SKILLSYNC_CV_ALLOWED_FORMATS", '["pdf"]')
    monkeypatch.setenv("SKILLSYNC_CV_STORAGE_ROOT", "/private/cvs")
    monkeypatch.setenv("SKILLSYNC_CV_PDF_MAX_PAGES", "12")
    monkeypatch.setenv("SKILLSYNC_CV_PDF_MAX_TEXT_CHARACTERS", "50000")
    monkeypatch.setenv("SKILLSYNC_CV_PDF_TIMEOUT_SECONDS", "2.5")

    settings = Settings()

    assert settings.app_name == "Configured API"
    assert settings.environment is Environment.STAGING
    assert settings.debug is True
    assert str(settings.database_url) == "postgresql+psycopg://app@database.example/skillsync"
    assert settings.cv_max_upload_bytes == 1048576
    assert settings.cv_allowed_formats == (CVFormat.PDF,)
    assert settings.cv_storage_root == Path("/private/cvs")
    assert settings.cv_pdf_max_pages == 12
    assert settings.cv_pdf_max_text_characters == 50_000
    assert settings.cv_pdf_timeout_seconds == 2.5


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("SKILLSYNC_CV_MAX_UPLOAD_BYTES", "0"),
        ("SKILLSYNC_CV_ALLOWED_FORMATS", "[]"),
        ("SKILLSYNC_CV_ALLOWED_FORMATS", '["docx"]'),
        ("SKILLSYNC_CV_PDF_MAX_PAGES", "0"),
        ("SKILLSYNC_CV_PDF_MAX_TEXT_CHARACTERS", "0"),
        ("SKILLSYNC_CV_PDF_TIMEOUT_SECONDS", "0"),
    ],
)
def test_settings_reject_an_unusable_cv_policy(
    monkeypatch: MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError):
        Settings()


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


def test_local_gets_a_development_secret() -> None:
    assert Settings(environment=Environment.LOCAL).session_secret == DEVELOPMENT_SESSION_SECRET


def test_the_development_secret_satisfies_the_floor_this_file_defines() -> None:
    """The fallback used to be a character under the minimum declared beside
    it, which is not a real weakness -- it is only ever used locally -- but it
    made PyJWT warn on every encode, and the file that sets the rule was the
    one breaking it."""
    assert len(DEVELOPMENT_SESSION_SECRET) >= MIN_SESSION_SECRET_LENGTH


def test_production_refuses_to_start_without_a_secret() -> None:
    with pytest.raises(ValueError, match="session secret"):
        Settings(environment=Environment.PRODUCTION)


def test_production_accepts_a_supplied_secret() -> None:
    settings = Settings(environment=Environment.PRODUCTION, session_secret="s" * 32)
    assert settings.session_secret == "s" * 32
    assert settings.session_cookie_secure is True


def test_the_session_lasts_an_hour_by_default() -> None:
    assert Settings(environment=Environment.LOCAL).session_lifetime_minutes == 60


def test_a_whitespace_only_secret_is_refused_outside_development() -> None:
    with pytest.raises(ValueError, match="session secret"):
        Settings(environment=Environment.PRODUCTION, session_secret="   ")


def test_a_secret_shorter_than_the_minimum_is_refused_outside_development() -> None:
    short_secret = "s" * (MIN_SESSION_SECRET_LENGTH - 1)
    with pytest.raises(ValueError, match="session secret"):
        Settings(environment=Environment.PRODUCTION, session_secret=short_secret)


def test_a_secret_of_exactly_the_minimum_length_is_accepted() -> None:
    secret = "s" * MIN_SESSION_SECRET_LENGTH
    settings = Settings(environment=Environment.PRODUCTION, session_secret=secret)
    assert settings.session_secret == secret


def test_local_keeps_an_explicitly_supplied_secret_rather_than_the_default() -> None:
    settings = Settings(environment=Environment.LOCAL, session_secret="s" * 32)
    assert settings.session_secret == "s" * 32
