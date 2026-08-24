from enum import StrEnum
from functools import lru_cache

from pydantic import PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    app_name: str = "SkillSync API"
    environment: Environment = Environment.LOCAL
    debug: bool = False
    database_url: PostgresDsn = PostgresDsn("postgresql+psycopg://localhost/skillsync")
    # Empty means unset. A usable default here would be a production
    # credential in the repository, so staging and production refuse to start
    # without one rather than quietly signing tokens with a known key.
    session_secret: str = ""
    session_lifetime_minutes: int = 60

    @field_validator("database_url")
    @classmethod
    def require_async_psycopg_driver(cls, database_url: PostgresDsn) -> PostgresDsn:
        if database_url.scheme != "postgresql+psycopg":
            raise ValueError("database URL must use the postgresql+psycopg scheme")
        return database_url

    @property
    def session_cookie_secure(self) -> bool:
        """Whether the cookie is HTTPS-only. Off locally so development works."""
        return self.environment not in (Environment.LOCAL, Environment.TEST)

    @model_validator(mode="after")
    def require_a_session_secret_outside_development(self) -> "Settings":
        if self.session_secret:
            return self
        if self.environment in (Environment.LOCAL, Environment.TEST):
            object.__setattr__(self, "session_secret", "development-only-session-secret")
            return self
        raise ValueError("a session secret is required outside local and test")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SKILLSYNC_",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
