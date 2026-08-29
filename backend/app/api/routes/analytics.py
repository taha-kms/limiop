"""Job-market aggregates over the public catalog.

Public, like the catalog they summarise. These are counts of postings anyone can
already read one at a time, so authenticating them would gate a summary of
public data behind an account.

Every handler is a call into the analytics service. No SQL and no arithmetic
lives here, so a wrong number is always wrong in one place.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_database_session
from app.modules.analytics.schemas import (
    AnalyticsQuery,
    LocationDistributionResponse,
    PostingTrendResponse,
    SkillDemandResponse,
    TrendQuery,
)
from app.modules.analytics.service import (
    read_location_distribution,
    read_posting_trend,
    read_skill_demand,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/skills", summary="Which skills the market is asking for")
async def read_skills(
    query: Annotated[AnalyticsQuery, Query()],
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> SkillDemandResponse:
    """Active jobs per canonical skill, most in demand first."""
    return await read_skill_demand(session, query)


@router.get("/locations", summary="Where the jobs are, and how they are worked")
async def read_locations(
    query: Annotated[AnalyticsQuery, Query()],
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> LocationDistributionResponse:
    """Active jobs per stated location, and the remote-hybrid-onsite split.

    Both keep what nobody stated: `Unknown` for a missing place and
    `unspecified` for a missing arrangement. A share computed over only the
    postings that answered is not a share of the market.
    """
    return await read_location_distribution(session, query)


@router.get("/trends", summary="How hiring activity moved")
async def read_trends(
    query: Annotated[TrendQuery, Query()],
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> PostingTrendResponse:
    """Jobs published per bucket, oldest first, in UTC."""
    return await read_posting_trend(session, query)
