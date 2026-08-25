"""Tests for idempotent local Airflow authentication initialization."""

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

BOOTSTRAP_PATH = Path(__file__).parents[1] / "bootstrap.py"
SPEC = spec_from_file_location("skillsync_airflow_bootstrap", BOOTSTRAP_PATH)
assert SPEC is not None and SPEC.loader is not None
BOOTSTRAP = module_from_spec(SPEC)
SPEC.loader.exec_module(BOOTSTRAP)


def test_authentication_files_are_created_once(monkeypatch, tmp_path: Path) -> None:
    jwt_secret_file = tmp_path / "jwt-secret"
    password_file = tmp_path / "passwords.json"
    monkeypatch.setenv("AIRFLOW_JWT_SECRET_FILE", str(jwt_secret_file))
    monkeypatch.setenv("AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE", str(password_file))
    monkeypatch.setenv("AIRFLOW_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AIRFLOW_ADMIN_PASSWORD", "local-test-password")

    BOOTSTRAP.create_authentication_files()
    first_jwt_secret = jwt_secret_file.read_text()
    first_passwords = password_file.read_text()
    BOOTSTRAP.create_authentication_files()

    assert jwt_secret_file.read_text() == first_jwt_secret
    assert password_file.read_text() == first_passwords
    assert set(json.loads(first_passwords)) == {"admin"}
    assert json.loads(first_passwords)["admin"] == "local-test-password"
    assert jwt_secret_file.stat().st_mode & 0o777 == 0o600
    assert password_file.stat().st_mode & 0o777 == 0o600


def test_metadata_database_must_not_be_the_skillsync_database(monkeypatch) -> None:
    monkeypatch.setenv("AIRFLOW_METADATA_DATABASE", "skillsync")
    monkeypatch.setenv("POSTGRES_DB", "skillsync")

    with pytest.raises(ValueError, match="database separate from SkillSync"):
        BOOTSTRAP.create_metadata_database()
