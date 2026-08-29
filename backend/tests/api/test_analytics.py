"""The public job-market aggregate endpoints."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
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

from app.modules.jobs.domain import JobStatus, WorkplaceType

pytestmark = pytest.mark.integration

ALIAS_VERSION = "analytics-api.test.1"
PYTHON = UUID("eeeeeeee-0000-4000-8000-000000000001")
SQL = UUID("eeeeeeee-0000-4000-8000-000000000002")
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
def market(database_url: PostgresDsn) -> Iterator[Engine]:
    engine = create_engine(str(database_url))
    wipe(engine)

    company_id, source_id = uuid4(), uuid4()
    specs: list[dict[str, Any]] = [
        {
            "title": "Remote Python",
            "location": "Berlin",
            "workplace_type": WorkplaceType.REMOTE,
            "published_at": JANUARY,
            "skills": (PYTHON, SQL),
        },
        {
            "title": "Onsite Python",
            "location": "Berlin",
            "workplace_type": WorkplaceType.ONSITE,
            "published_at": FEBRUARY,
            "skills": (PYTHON,),
        },
        {
            "title": "Placeless",
            "location": None,
            "workplace_type": WorkplaceType.UNSPECIFIED,
            "published_at": FEBRUARY,
            "skills": (),
        },
        {
            "title": "Gone",
            "location": "Berlin",
            "workplace_type": WorkplaceType.REMOTE,
            "published_at": JANUARY,
            "status": JobStatus.EXPIRED,
            "skills": (PYTHON, SQL),
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
        connection.execute(
            insert(JobSkill),
            [
                {
                    "job_id": ids[spec["title"]],
                    "concept_id": concept,
                    "alias_version": ALIAS_VERSION,
                    "surface_form": CONCEPTS[concept],
                }
                for spec in specs
                for concept in spec["skills"]
            ],
        )

    try:
        yield engine
    finally:
        wipe(engine)
        engine.dispose()


def read(client: TestClient, path: str, **params: Any) -> dict[str, Any]:
    response = client.get(f"/api/v1/analytics{path}", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_the_aggregates_are_public_like_the_catalog_they_summarise(
    migrated_client: TestClient, market: Engine
) -> None:
    """Counts of postings anyone can already read one at a time."""
    for path in ("/skills", "/locations", "/trends"):
        assert migrated_client.get(f"/api/v1/analytics{path}").status_code == 200


def test_skill_demand_ranks_the_active_market(migrated_client: TestClient, market: Engine) -> None:
    body = read(migrated_client, "/skills")

    assert [(skill["preferred_label"], skill["jobs"]) for skill in body["skills"]] == [
        ("Python", 2),
        ("SQL", 1),
    ]


def test_locations_keep_the_postings_that_stated_nothing(
    migrated_client: TestClient, market: Engine
) -> None:
    body = read(migrated_client, "/locations")

    assert {row["location"]: row["jobs"] for row in body["locations"]} == {
        "Berlin": 2,
        "Unknown": 1,
    }
    assert {row["workplace_type"]: row["jobs"] for row in body["workplace_types"]} == {
        "remote": 1,
        "onsite": 1,
        "unspecified": 1,
    }


def test_a_trend_echoes_the_bucket_it_was_cut_with(
    migrated_client: TestClient, market: Engine
) -> None:
    """A series of counts means nothing without knowing what a point is."""
    body = read(migrated_client, "/trends", bucket="month")

    assert body["bucket"] == "month"
    assert [point["jobs"] for point in body["points"]] == [1, 2]


def test_a_window_narrows_every_aggregate(migrated_client: TestClient, market: Engine) -> None:
    window = {"since": "2026-02-01T00:00:00Z", "until": "2026-03-01T00:00:00Z"}

    assert [s["jobs"] for s in read(migrated_client, "/skills", **window)["skills"]] == [1]
    assert read(migrated_client, "/trends", bucket="day", **window)["points"] == [
        {"bucket_start": "2026-02-05T00:00:00Z", "jobs": 2}
    ]


def test_an_empty_period_is_an_empty_result_rather_than_an_error(
    migrated_client: TestClient, market: Engine
) -> None:
    window = {"since": "2030-01-01T00:00:00Z", "until": "2030-02-01T00:00:00Z"}

    assert read(migrated_client, "/skills", **window)["skills"] == []
    assert read(migrated_client, "/locations", **window)["locations"] == []
    assert read(migrated_client, "/trends", **window)["points"] == []


def test_a_window_ending_before_it_starts_is_refused(
    migrated_client: TestClient, market: Engine
) -> None:
    """Returning nothing would be defensible and useless: a caller would read
    it as a market with no postings in it."""
    response = migrated_client.get(
        "/api/v1/analytics/skills",
        params={"since": "2026-03-01T00:00:00Z", "until": "2026-01-01T00:00:00Z"},
    )

    assert response.status_code == 422
    assert "until must be after since" in response.text


def test_an_unsupported_bucket_is_refused(migrated_client: TestClient, market: Engine) -> None:
    assert (
        migrated_client.get("/api/v1/analytics/trends", params={"bucket": "fortnight"}).status_code
        == 422
    )


def test_a_misspelled_filter_is_refused_rather_than_ignored(
    migrated_client: TestClient, market: Engine
) -> None:
    """A dropped filter returns the whole market and looks like a match."""
    assert (
        migrated_client.get("/api/v1/analytics/skills", params={"sources": "arbeitnow"}).status_code
        == 422
    )


def test_an_unusable_limit_is_refused(migrated_client: TestClient, market: Engine) -> None:
    assert migrated_client.get("/api/v1/analytics/skills", params={"limit": 0}).status_code == 422
    assert (
        migrated_client.get("/api/v1/analytics/skills", params={"limit": 1000}).status_code == 422
    )
