"""Reading the job-market aggregates.

Thin on purpose. Every calculation is a statement in `queries`, and this turns
rows into the served shapes so a handler contains no SQL and no arithmetic.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics import queries
from app.modules.analytics.queries import AnalyticsFilters
from app.modules.analytics.schemas import (
    AnalyticsQuery,
    LocationCount,
    LocationDistributionResponse,
    PostingTrendResponse,
    SkillDemand,
    SkillDemandResponse,
    TrendPoint,
    TrendQuery,
    WorkplaceCount,
)


def filters_of(query: AnalyticsQuery) -> AnalyticsFilters:
    return AnalyticsFilters(
        since=query.since,
        until=query.until,
        source_key=query.source_key,
        location=query.location,
    )


async def read_skill_demand(session: AsyncSession, query: AnalyticsQuery) -> SkillDemandResponse:
    rows = await session.execute(queries.skill_demand(filters_of(query), query.limit))
    return SkillDemandResponse(
        skills=tuple(
            SkillDemand(concept_id=row[0], preferred_label=row[1], jobs=row[2]) for row in rows
        )
    )


async def read_location_distribution(
    session: AsyncSession, query: AnalyticsQuery
) -> LocationDistributionResponse:
    filters = filters_of(query)
    locations = await session.execute(queries.location_distribution(filters, query.limit))
    workplaces = await session.execute(queries.workplace_distribution(filters))
    return LocationDistributionResponse(
        locations=tuple(LocationCount(location=row[0], jobs=row[1]) for row in locations),
        workplace_types=tuple(
            WorkplaceCount(workplace_type=row[0], jobs=row[1]) for row in workplaces
        ),
    )


async def read_posting_trend(session: AsyncSession, query: TrendQuery) -> PostingTrendResponse:
    rows = await session.execute(queries.posting_trend(filters_of(query), query.bucket))
    return PostingTrendResponse(
        bucket=query.bucket,
        points=tuple(TrendPoint(bucket_start=row[0], jobs=row[1]) for row in rows),
    )
