"""Registration, and the sessions that follow it."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import SESSION_COOKIE, get_application_settings, get_database_session
from app.core.config import Settings
from app.modules.accounts.schemas import AccountRead, LoginRequest, RegistrationRequest
from app.modules.accounts.service import EmailAlreadyRegistered, authenticate, register
from app.modules.accounts.tokens import SessionClaims, issue_token

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])
sessions_router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(
    request: RegistrationRequest,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> AccountRead:
    try:
        user = await register(session, request)
    except EmailAlreadyRegistered:
        # Deliberately the same wording whatever went wrong, and no echo of the
        # address, so this cannot be used to enumerate who has an account.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="that account cannot be created"
        ) from None
    return AccountRead.model_validate(user)


@sessions_router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def log_in(
    request: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> None:
    user = await authenticate(session, request.email, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="those credentials were not accepted"
        )
    token = issue_token(
        SessionClaims(user_id=user.id, token_version=user.token_version),
        secret=settings.session_secret,
        lifetime_minutes=settings.session_lifetime_minutes,
        now=datetime.now(UTC),
    )
    # The token goes only into the cookie. Putting it in the body as well would
    # hand it to any script on the page, which is what HttpOnly is preventing.
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_lifetime_minutes * 60,
        path="/",
    )
