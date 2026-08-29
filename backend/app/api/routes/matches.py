"""Ranked jobs for the signed-in candidate.

A second endpoint rather than a viewer-dependent listing. The public catalogue
stays exactly as public and as cacheable as it was, and a per-viewer ordering
that could never be shared-cached is kept off it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_database_session
from app.modules.matching.schemas import MatchListQuery, MatchListResponse
from app.modules.matching.service import rank_jobs_for

router = APIRouter(prefix="/api/v1/matches", tags=["matching"])


@router.get("", summary="Rank the catalog against your profile")
async def read_matches(
    query: Annotated[MatchListQuery, Query()],
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> MatchListResponse:
    """Return the best matches for the signed-in candidate, highest first.

    Scoped by the session rather than by a parameter: there is no identifier a
    caller could supply to read somebody else's matches.

    A profile with too few skills to rank returns nothing. Ranking a whole
    catalogue against one generic skill produces an order that looks considered
    and is not, which is worse than an empty answer.
    """
    return await rank_jobs_for(session, user.id, query.limit)
