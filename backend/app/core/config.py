from enum import StrEnum
from functools import lru_cache

from pydantic import PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


# A secret shorter than this is guessable by brute force against an HMAC, so
# staging and production are refused one below this length the same way they
# are refused an empty one.
MIN_SESSION_SECRET_LENGTH = 32


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
        # Stripped so a whitespace-only value (e.g. an env var set to a
        # single space) is treated exactly like an empty one, rather than
        # passing the truthiness check below and becoming the signing key.
        secret = self.session_secret.strip()
        if self.environment in (Environment.LOCAL, Environment.TEST):
            if not secret:
                object.__setattr__(self, "session_secret", "development-only-session-secret")
            return self
        if not secret:
            raise ValueError("a session secret is required outside local and test")
        if len(secret) < MIN_SESSION_SECRET_LENGTH:
            raise ValueError(
                f"a session secret must be at least {MIN_SESSION_SECRET_LENGTH} characters"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SKILLSYNC_",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
