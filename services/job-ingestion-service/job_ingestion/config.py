"""Environment-backed settings for the ingestion service."""

import os
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PostgresDsn, TypeAdapter

DATABASE_URL_ENV = "SKILLSYNC_DATABASE_URL"
SOURCE_CONFIG_ENV = "SKILLSYNC_SOURCE_CONFIG"
DEFAULT_DATABASE_URL = "postgresql+psycopg://localhost/skillsync"

type SourceConfig = dict[str, dict[str, JsonValue]]

_SOURCE_CONFIG_ADAPTER: TypeAdapter[SourceConfig] = TypeAdapter(SourceConfig)


def _database_url_from_environment() -> PostgresDsn:
    return PostgresDsn(os.getenv(DATABASE_URL_ENV, DEFAULT_DATABASE_URL))


def _source_config_from_environment() -> SourceConfig:
    return _SOURCE_CONFIG_ADAPTER.validate_json(os.getenv(SOURCE_CONFIG_ENV, "{}"))


class Settings(BaseModel):
    database_url: PostgresDsn = Field(default_factory=_database_url_from_environment)
    source_config: SourceConfig = Field(default_factory=_source_config_from_environment)

    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
