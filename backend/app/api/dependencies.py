from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import Database

# Declared here because both the route that sets it and the dependency that
# reads it need the same name, and two copies is one rename away from a bug.
SESSION_COOKIE = "session"


def get_database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


async def get_database_session(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async with database.session() as session:
        yield session


def get_application_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)
