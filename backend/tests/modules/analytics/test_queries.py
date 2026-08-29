"""Job-market aggregates over the canonical catalog."""

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from platform_db.models import (
    Company,
    Job,
    JobProvenance,
    JobSource,
    SkillAliasVersion,
    SkillConcept,
)
from platform_db.models.job_skills import JobSkill
from pydantic import PostgresDsn
from sqlalchemy import Engine, create_engine, delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Database
from app.modules.analytics.queries import (
    UNKNOWN_LOCATION,
    AnalyticsFilters,
    TrendBucket,
    location_distribution,
    posting_trend,
    skill_demand,
    workplace_distribution,
)
from app.modules.jobs.domain import JobStatus, WorkplaceType

pytestmark = pytest.mark.integration

ALIAS_VERSION = "analytics.test.1"
PYTHON = UUID("dddddddd-0000-4000-8000-000000000001")
SQL = UUID("dddddddd-0000-4000-8000-000000000002")
CONCEPTS = {PYTHON: "Python", SQL: "SQL"}

JANUARY = datetime(2026, 1, 5, 12, tzinfo=UTC)
FEBRUARY = datetime(2026, 2, 5, 12, tzinfo=UTC)


def wipe(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(delete(JobSkill))
        connection.execute(delete(JobProvenance))
        connection.execute(delete(Job))
        connection.execute(delete(Company))
        connection.execute(delete(JobSource))
        connection.execute(delete(SkillConcept).where(SkillConcept.id.in_(CONCEPTS)))
        connection.execute(
            delete(SkillAliasVersion).where(SkillAliasVersion.version == ALIAS_VERSION)
        )


@pytest.fixture
def catalog(database_url: PostgresDsn) -> Iterator[Engine]:
    """A small catalog with known skills, places, arrangements and dates."""
    engine = create_engine(str(database_url))
    wipe(engine)

    company_id, source_id = uuid4(), uuid4()
    specs: list[dict[str, Any]] = [
        {
            "title": "Berlin remote",
            "location": "Berlin",
            "workplace_type": WorkplaceType.REMOTE,
            "published_at": JANUARY,
            "skills": (PYTHON, SQL),
        },
        {
            "title": "Berlin onsite",
            "location": "Berlin",
            "workplace_type": WorkplaceType.ONSITE,
            "published_at": JANUARY,
            "skills": (PYTHON,),
        },
        {
            "title": "Nowhere",
            "location": None,
            "workplace_type": WorkplaceType.UNSPECIFIED,
            "published_at": FEBRUARY,
            "skills": (),
        },
        {
            "title": "Undated",
            "location": "Munich",
            "workplace_type": WorkplaceType.UNSPECIFIED,
            "published_at": None,
            "skills": (SQL,),
        },
        {
            "title": "Expired",
            "location": "Berlin",
            "workplace_type": WorkplaceType.REMOTE,
            "published_at": JANUARY,
            "status": JobStatus.EXPIRED,
            "skills": (PYTHON,),
        },
    ]

    ids = {spec["title"]: uuid4() for spec in specs}
    with engine.begin() as connection:
        connection.execute(insert(SkillAliasVersion), [{"version": ALIAS_VERSION}])
        connection.execute(
            insert(JobSource),
            [
                {
                    "id": source_id,
                    "key": "arbeitnow",
                    "display_name": "Arbeitnow",
                    "base_url": "https://www.arbeitnow.com/api/job-board-api",
                }
            ],
        )
        connection.execute(
            insert(Company),
            [{"id": company_id, "display_name": "Acme GmbH", "normalized_name": "acme gmbh"}],
        )
        connection.execute(
            insert(SkillConcept),
            [{"id": concept, "preferred_label": label} for concept, label in CONCEPTS.items()],
        )
        connection.execute(
            insert(Job),
            [
                {
                    "id": ids[spec["title"]],
                    "company_id": company_id,
                    "match_key": f"v1:{uuid4().hex}",
                    "title": spec["title"],
                    "description": "Work.",
                    "application_url": "https://acme.example.com/apply",
                    "location": spec["location"],
                    "workplace_type": spec["workplace_type"],
                    "published_at": spec["published_at"],
                    "status": spec.get("status", JobStatus.ACTIVE),
                }
                for spec in specs
            ],
        )
        connection.execute(
            insert(JobProvenance),
            [
                {
                    "job_id": ids[spec["title"]],
                    "source_id": source_id,
                    "source_job_id": spec["title"],
                    "source_url": "https://acme.example.com/apply",
                    "first_seen_at": JANUARY,
                    "last_seen_at": JANUARY,
                }
                for spec in specs
            ],
        )
        rows = [
            {
                "job_id": ids[spec["title"]],
                "concept_id": concept,
                "alias_version": ALIAS_VERSION,
                "surface_form": CONCEPTS[concept],
            }
            for spec in specs
            for concept in spec["skills"]
        ]
        if rows:
            connection.execute(insert(JobSkill), rows)

    try:
        yield engine
    finally:
        wipe(engine)
        engine.dispose()


def rows(database_url: PostgresDsn, work: Callable[[AsyncSession], Awaitable[Any]]) -> Any:
    async def go() -> Any:
        database = Database(database_url)
        try:
            async with database.session() as session:
                return await work(session)
        finally:
            await database.dispose()

    return asyncio.run(go())


def fetch(database_url: PostgresDsn, statement: Any) -> list[Any]:
    async def work(session: AsyncSession) -> list[Any]:
        return list(await session.execute(statement))

    result: list[Any] = rows(database_url, work)
    return result


def test_skill_demand_counts_jobs_per_concept(database_url: PostgresDsn, catalog: Engine) -> None:
    result = fetch(database_url, skill_demand(AnalyticsFilters(), limit=10))

    assert [(row[1], row[2]) for row in result] == [("Python", 2), ("SQL", 2)]


def test_an_expired_posting_is_not_current_demand(
    database_url: PostgresDsn, catalog: Engine
) -> None:
    """The expired job asks for Python too, and is excluded, so Python is 2."""
    result = fetch(database_url, skill_demand(AnalyticsFilters(), limit=10))

    assert dict((row[1], row[2]) for row in result)["Python"] == 2


def test_skill_demand_is_empty_over_a_period_with_no_postings(
    database_url: PostgresDsn, catalog: Engine
) -> None:
    window = AnalyticsFilters(
        since=datetime(2030, 1, 1, tzinfo=UTC), until=datetime(2030, 2, 1, tzinfo=UTC)
    )

    assert fetch(database_url, skill_demand(window, limit=10)) == []


def test_a_window_is_inclusive_at_the_start_and_exclusive_at_the_end(
    database_url: PostgresDsn, catalog: Engine
) -> None:
    """Adjacent windows tile without counting a posting twice at the seam."""
    january = AnalyticsFilters(since=JANUARY, until=FEBRUARY)
    february = AnalyticsFilters(since=FEBRUARY, until=datetime(2026, 3, 1, tzinfo=UTC))

    assert [row[2] for row in fetch(database_url, skill_demand(january, limit=10))] == [2, 1]
    assert fetch(database_url, skill_demand(february, limit=10)) == []


def test_a_location_nobody_stated_stays_visible(database_url: PostgresDsn, catalog: Engine) -> None:
    """A silently smaller denominator makes every other row wrong."""
    result = fetch(database_url, location_distribution(AnalyticsFilters(), limit=10))

    assert dict(result) == {"Berlin": 2, "Munich": 1, UNKNOWN_LOCATION: 1}


def test_locations_are_grouped_exactly_as_stored(
    database_url: PostgresDsn, catalog: Engine
) -> None:
    """Normalizing here would invent a taxonomy nobody decided."""
    result = fetch(database_url, location_distribution(AnalyticsFilters(), limit=10))

    assert "Berlin" in dict(result)
    assert not any(row[0].endswith("Germany") for row in result)


def test_the_workplace_split_keeps_the_postings_that_said_nothing(
    database_url: PostgresDsn, catalog: Engine
) -> None:
    """Otherwise the remote share is a share of the postings that answered."""
    result = fetch(database_url, workplace_distribution(AnalyticsFilters()))

    assert dict(result) == {
        WorkplaceType.UNSPECIFIED: 2,
        WorkplaceType.REMOTE: 1,
        WorkplaceType.ONSITE: 1,
    }


@pytest.mark.parametrize(
    ("bucket", "expected"),
    [
        (
            TrendBucket.DAY,
            [(datetime(2026, 1, 5, tzinfo=UTC), 2), (datetime(2026, 2, 5, tzinfo=UTC), 1)],
        ),
        (
            TrendBucket.MONTH,
            [(datetime(2026, 1, 1, tzinfo=UTC), 2), (datetime(2026, 2, 1, tzinfo=UTC), 1)],
        ),
    ],
)
def test_a_trend_buckets_by_publication_date(
    database_url: PostgresDsn,
    catalog: Engine,
    bucket: TrendBucket,
    expected: list[tuple[datetime, int]],
) -> None:
    result = fetch(database_url, posting_trend(AnalyticsFilters(), bucket))

    assert [(row[0].replace(tzinfo=UTC), row[1]) for row in result] == expected


def test_weekly_buckets_start_on_the_same_day_every_time(
    database_url: PostgresDsn, catalog: Engine
) -> None:
    result = fetch(database_url, posting_trend(AnalyticsFilters(), TrendBucket.WEEK))

    # PostgreSQL truncates a week to its Monday, so the boundary is stated
    # rather than being whatever the first posting happened to fall on.
    assert [row[0].weekday() for row in result] == [0, 0]


def test_an_undated_posting_belongs_to_no_period(
    database_url: PostgresDsn, catalog: Engine
) -> None:
    """Bucketing it somewhere would be an invention a chart cannot see."""
    result = fetch(database_url, posting_trend(AnalyticsFilters(), TrendBucket.MONTH))

    assert sum(row[1] for row in result) == 3


def test_a_trend_is_ordered_oldest_first(database_url: PostgresDsn, catalog: Engine) -> None:
    result = fetch(database_url, posting_trend(AnalyticsFilters(), TrendBucket.DAY))

    assert [row[0] for row in result] == sorted(row[0] for row in result)


def test_a_source_filter_narrows_every_aggregate(
    database_url: PostgresDsn, catalog: Engine
) -> None:
    matching = AnalyticsFilters(source_key="arbeitnow")
    absent = AnalyticsFilters(source_key="greenhouse")

    assert fetch(database_url, skill_demand(matching, limit=10)) != []
    assert fetch(database_url, skill_demand(absent, limit=10)) == []
    assert fetch(database_url, location_distribution(absent, limit=10)) == []
    assert fetch(database_url, posting_trend(absent, TrendBucket.DAY)) == []


def test_a_location_filter_narrows_every_aggregate(
    database_url: PostgresDsn, catalog: Engine
) -> None:
    berlin = AnalyticsFilters(location="Berlin")

    assert dict(fetch(database_url, location_distribution(berlin, limit=10))) == {"Berlin": 2}
    assert [row[2] for row in fetch(database_url, skill_demand(berlin, limit=10))] == [2, 1]


def test_a_limit_keeps_the_ranking_reproducible(database_url: PostgresDsn, catalog: Engine) -> None:
    """Equal counts break on the label, so a cut-off chart is stable."""
    first = fetch(database_url, skill_demand(AnalyticsFilters(), limit=1))
    again = fetch(database_url, skill_demand(AnalyticsFilters(), limit=1))

    assert first == again
    assert first[0][1] == "Python"
