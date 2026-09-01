"""The signed-in account. Also the smallest possible proof the session works."""

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
)
from app.api.throttle import AttemptThrottle, account_key
from app.core.config import Settings
from app.modules.accounts.schemas import AccountDeletionRequest, AccountRead
from app.modules.accounts.service import PasswordNotConfirmed, delete_account
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
