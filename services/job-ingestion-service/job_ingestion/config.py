"""Environment-backed settings for the ingestion service."""

import os
from enum import StrEnum
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PostgresDsn, TypeAdapter

DATABASE_URL_ENV = "SKILLSYNC_DATABASE_URL"
SOURCE_CONFIG_ENV = "SKILLSYNC_SOURCE_CONFIG"
SKILL_ALIAS_VERSION_ENV = "SKILLSYNC_SKILL_ALIAS_VERSION"
DEFAULT_DATABASE_URL = "postgresql+psycopg://localhost/skillsync"

type SourceConfig = dict[str, dict[str, JsonValue]]

_SOURCE_CONFIG_ADAPTER: TypeAdapter[SourceConfig] = TypeAdapter(SourceConfig)


class Environment(StrEnum):
    """Execution environment retained by the moved pipeline test contract."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


def _database_url_from_environment() -> PostgresDsn:
    return PostgresDsn(os.getenv(DATABASE_URL_ENV, DEFAULT_DATABASE_URL))


def _source_config_from_environment() -> SourceConfig:
    return _SOURCE_CONFIG_ADAPTER.validate_json(os.getenv(SOURCE_CONFIG_ENV, "{}"))


def _skill_alias_version_from_environment() -> str | None:
    return os.getenv(SKILL_ALIAS_VERSION_ENV) or None


class Settings(BaseModel):
    database_url: PostgresDsn = Field(default_factory=_database_url_from_environment)
    source_config: SourceConfig = Field(default_factory=_source_config_from_environment)
    environment: Environment = Environment.LOCAL
    # Which published alias table extraction runs under. None follows the newest
    # one, which is what a deployment wants; pin it to stop a publication from
    # silently re-extracting the whole catalog on the next run.
    skill_alias_version: str | None = Field(default_factory=_skill_alias_version_from_environment)

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
