from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.throttle import AttemptThrottle
from app.core.config import Settings
from app.db.session import Database
from app.modules.accounts.models import User
from app.modules.accounts.tokens import read_token
from app.modules.cvs.storage import CVStorage

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


def get_cv_storage(request: Request) -> CVStorage:
    return cast(CVStorage, request.app.state.cv_storage)


def get_attempt_throttle(request: Request) -> AttemptThrottle:
    return cast(AttemptThrottle, request.app.state.attempt_throttle)


def refuse_exhausted_attempts(throttle: AttemptThrottle, key: str) -> None:
    """Stop a caller who has spent this account's attempts.

    Called before the work being protected, which is the password hash: a
    handler that has started hashing has already paid for the attempt.
    """
    retry_after = throttle.retry_after(key)
    if retry_after is None:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        # The same words whether or not the account exists, like every other
        # rejection on these two endpoints.
        detail="too many attempts; try again later",
        headers={"Retry-After": str(retry_after)},
    )


def _unauthorised() -> HTTPException:
    """A fresh rejection, built at each raise site.

    The wording lives here rather than at the raise sites so every branch of
    `current_user` stays indistinguishable, but the object must not be shared:
    CPython appends a frame to an exception's `__traceback__` on every `raise`
    of that object, and a module-level instance is never collected, so a
    shared one accumulates every rejected request's frames -- and the
    `Request`, ASGI scope and resolved dependencies those frames pin -- for
    the life of the process.
    """
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not signed in")


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
        raise _unauthorised()
    claims = read_token(token, secret=settings.session_secret, now=datetime.now(UTC))
    if claims is None:
        raise _unauthorised()
    found = await session.execute(select(User).where(User.id == claims.user_id))
    user = found.scalars().first()
    if user is None or not user.is_active:
        raise _unauthorised()
    # The generation check. A token issued before a password change carries the
    # old number and stops here.
    if user.token_version != claims.token_version:
        raise _unauthorised()
    return user


CurrentUser = Annotated[User, Depends(current_user)]
