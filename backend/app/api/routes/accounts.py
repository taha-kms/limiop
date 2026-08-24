"""Registration."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_database_session
from app.modules.accounts.schemas import AccountRead, RegistrationRequest
from app.modules.accounts.service import EmailAlreadyRegistered, register

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


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
