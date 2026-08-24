from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.modules.cvs.policy import DEFAULT_CV_MAX_UPLOAD_BYTES, CVFormat


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


# A secret shorter than this is guessable by brute force against an HMAC, so
# staging and production are refused one below this length the same way they
# are refused an empty one.
MIN_SESSION_SECRET_LENGTH = 32

# Not a secret: it is in the repository, and it exists only so local
# development and the test suite have *a* signing key. It is over the floor
# above because PyJWT warns on every encode with a shorter HMAC key, and a
# warning on every request is a warning readers stop reading.
DEVELOPMENT_SESSION_SECRET = "local-development-only-session-secret"


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
    cv_max_upload_bytes: int = Field(default=DEFAULT_CV_MAX_UPLOAD_BYTES, gt=0)
    cv_allowed_formats: Annotated[tuple[CVFormat, ...], Field(min_length=1)] = (CVFormat.PDF,)
    cv_storage_root: Path = Path("uploads/cvs")
    cv_pdf_max_pages: int = Field(default=20, gt=0)
    cv_pdf_max_text_characters: int = Field(default=100_000, gt=0)
    cv_pdf_timeout_seconds: float = Field(default=5.0, gt=0)

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
                object.__setattr__(self, "session_secret", DEVELOPMENT_SESSION_SECRET)
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
