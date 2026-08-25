"""Service adapter for the shared database session factory."""

from platform_db.session import Database as PlatformDatabase
from pydantic import PostgresDsn


class Database(PlatformDatabase):
    """Accept the validated database URL used by service settings and tests."""

    def __init__(self, database_url: PostgresDsn | str) -> None:
        super().__init__(str(database_url))
