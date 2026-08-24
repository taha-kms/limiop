from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import Database
from app.modules.accounts.models import User
from app.modules.accounts.tokens import read_token

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


_UNAUTHORISED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not signed in")


async def current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> User:
    """The signed-in account, or a 401.

    Every rejection is the same response. A caller learning why a token failed
    learns whether an account exists and whether it is disabled, which is not
    information an unauthenticated request should be able to buy.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _UNAUTHORISED
    claims = read_token(token, secret=settings.session_secret, now=datetime.now(UTC))
    if claims is None:
        raise _UNAUTHORISED
    found = await session.execute(select(User).where(User.id == claims.user_id))
    user = found.scalars().first()
    if user is None or not user.is_active:
        raise _UNAUTHORISED
    # The generation check. A token issued before a password change carries the
    # old number and stops here.
    if user.token_version != claims.token_version:
        raise _UNAUTHORISED
    return user


CurrentUser = Annotated[User, Depends(current_user)]
