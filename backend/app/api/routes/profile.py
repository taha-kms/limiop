"""The signed-in candidate's route-neutral profile."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_database_session
from app.modules.profiles.schemas import CandidateProfileRead, CandidateProfileUpdate
from app.modules.profiles.service import find_profile, save_profile

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


@router.get("")
async def read_profile(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> CandidateProfileRead:
    profile = await find_profile(session, user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not started")
    return CandidateProfileRead.model_validate(profile)


@router.patch("")
async def update_profile(
    update: CandidateProfileUpdate,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> CandidateProfileRead:
    profile = await save_profile(session, user.id, update)
    return CandidateProfileRead.model_validate(profile)
