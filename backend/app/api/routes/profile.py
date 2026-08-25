"""The signed-in candidate's route-neutral profile."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_database_session
from app.modules.profiles.models import CandidateProfileSkill
from app.modules.profiles.schemas import (
    CandidateProfileRead,
    CandidateProfileSkillCreate,
    CandidateProfileSkillRead,
    CandidateProfileUpdate,
    SkillConceptRead,
    SkillTerm,
)
from app.modules.profiles.service import (
    ProfileNotFound,
    SkillCatalogUnavailable,
    SkillRefusalReason,
    SkillTermRefused,
    add_profile_skill,
    add_profile_skill_by_concept_id,
    find_profile,
    list_profile_skills,
    remove_profile_skill,
    save_profile,
    search_skill_concepts,
)

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


def _skill_read(skill: CandidateProfileSkill) -> CandidateProfileSkillRead:
    return CandidateProfileSkillRead(
        concept_id=skill.concept_id,
        preferred_label=skill.concept.preferred_label,
        vocabulary_version=skill.vocabulary_version,
        created_at=skill.created_at,
    )


@router.get("/skills")
async def read_profile_skills(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> list[CandidateProfileSkillRead]:
    try:
        skills = await list_profile_skills(session, user.id)
    except ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="profile not started"
        ) from None
    return [_skill_read(skill) for skill in skills]


@router.get("/skills/search")
async def search_profile_skill_concepts(
    q: Annotated[SkillTerm, Query()],
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> list[SkillConceptRead]:
    concepts = await search_skill_concepts(session, q)
    return [
        SkillConceptRead(concept_id=concept.id, preferred_label=concept.preferred_label)
        for concept in concepts
    ]


@router.post("/skills", status_code=status.HTTP_201_CREATED)
async def create_profile_skill(
    request: CandidateProfileSkillCreate,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> CandidateProfileSkillRead:
    try:
        if request.concept_id is not None:
            skill = await add_profile_skill_by_concept_id(session, user.id, request.concept_id)
        else:
            assert request.term is not None
            skill = await add_profile_skill(session, user.id, request.term)
    except ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="profile not started"
        ) from None
    except SkillTermRefused as error:
        messages = {
            SkillRefusalReason.AMBIGUOUS: (
                "the skill term is ambiguous; select a more specific vocabulary skill"
            ),
            SkillRefusalReason.UNMAPPED: (
                "the skill term is not in the canonical vocabulary; select a listed skill"
            ),
        }
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": error.reason.value, "message": messages[error.reason]},
        ) from None
    except SkillCatalogUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="the canonical skill catalog is unavailable",
        ) from None
    return _skill_read(skill)


@router.delete("/skills/{concept_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile_skill(
    concept_id: UUID,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> None:
    try:
        removed = await remove_profile_skill(session, user.id, concept_id)
    except ProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="profile not started"
        ) from None
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile skill not found")
