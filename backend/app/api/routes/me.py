"""The signed-in account. Also the smallest possible proof the session works."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    SESSION_COOKIE,
    CurrentUser,
    get_application_settings,
    get_attempt_throttle,
    get_cv_storage,
    get_database_session,
    refuse_exhausted_attempts,
    set_session_cookie,
)
from app.api.throttle import AttemptThrottle, account_key
from app.core.config import Settings
from app.modules.accounts.schemas import (
    AccountDeletionRequest,
    AccountRead,
    PasswordChangeRequest,
)
from app.modules.accounts.service import PasswordNotConfirmed, change_password, delete_account
from app.modules.accounts.tokens import SessionClaims, issue_token
from app.modules.cvs.storage import CVStorage, CVStorageError

router = APIRouter(prefix="/api/v1/me", tags=["accounts"])


@router.get("")
async def read_me(user: CurrentUser) -> AccountRead:
    return AccountRead.model_validate(user)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your account and everything it owns",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication is required"},
        status.HTTP_403_FORBIDDEN: {"description": "The password was not confirmed"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Too many attempts on this account"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "The account could not be deleted"},
    },
)
async def delete_me(
    request: AccountDeletionRequest,
    user: CurrentUser,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_application_settings)],
    storage: Annotated[CVStorage, Depends(get_cv_storage)],
    throttle: Annotated[AttemptThrottle, Depends(get_attempt_throttle)],
) -> None:
    """Delete the caller's account, its profile, its skills, and its CVs.

    Nothing is kept and nothing is recoverable. The session cookie is cleared
    on the way out, and the token stops working wherever it is still held,
    because the account it names is gone.

    The confirmation is bounded like the other two password checks. It costs the
    same argon2 hash, and a gate that guards something irreversible is the last
    one to leave unbounded.
    """
    key = account_key("sessions", user.email)
    refuse_exhausted_attempts(throttle, key)
    try:
        await delete_account(session, storage, user=user, password=request.password)
    except PasswordNotConfirmed:
        throttle.record(key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="that password was not accepted",
        ) from None
    except CVStorageError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="the account could not be deleted",
        ) from None

    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Replace your password and sign every other device out",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication is required"},
        status.HTTP_403_FORBIDDEN: {"description": "The current password was not confirmed"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Too many attempts on this account"},
    },
)
async def change_my_password(
    request: PasswordChangeRequest,
    user: CurrentUser,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_application_settings)],
    throttle: Annotated[AttemptThrottle, Depends(get_attempt_throttle)],
) -> None:
    """Replace the caller's password.

    Every session the account had ends, which is the point: somebody changing a
    password they think is known needs the sessions it opened to stop working.
    The browser doing the changing is then re-issued a cookie under the new
    version, because signing somebody out of the device they are holding is a
    cost with nothing to buy.

    Bounded like the other password checks, and for more reason than they have:
    this is the only route that pays for two argon2 hashes, one to check the
    old password and one to store the new.
    """
    key = account_key("sessions", user.email)
    refuse_exhausted_attempts(throttle, key)
    try:
        version = await change_password(
            session,
            user=user,
            current_password=request.current_password,
            new_password=request.new_password,
        )
    except PasswordNotConfirmed:
        throttle.record(key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="that password was not accepted",
        ) from None

    token = issue_token(
        SessionClaims(user_id=user.id, token_version=version),
        secret=settings.session_secret,
        lifetime_minutes=settings.session_lifetime_minutes,
        now=datetime.now(UTC),
    )
    set_session_cookie(response, token, settings)
