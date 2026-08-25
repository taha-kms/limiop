from importlib import import_module, util

from pytest import MonkeyPatch

from job_ingestion.config import Settings


def test_package_imports() -> None:
    package = import_module("job_ingestion")

    assert package.__name__ == "job_ingestion"


def test_web_and_backend_modules_are_not_importable() -> None:
    assert util.find_spec("fastapi") is None
    assert util.find_spec("app") is None


def test_settings_read_database_and_source_configuration(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SKILLSYNC_DATABASE_URL",
        "postgresql+psycopg://ingestion@database.example/skillsync",
    )
    monkeypatch.setenv(
        "SKILLSYNC_SOURCE_CONFIG",
        '{"arbeitnow":{"max_pages":5},"greenhouse":{"boards":["example"]}}',
    )

    settings = Settings()

    assert str(settings.database_url) == (
        "postgresql+psycopg://ingestion@database.example/skillsync"
    )
    assert settings.source_config == {
        "arbeitnow": {"max_pages": 5},
        "greenhouse": {"boards": ["example"]},
    }
