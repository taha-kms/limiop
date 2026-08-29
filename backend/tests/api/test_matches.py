"""Ranked jobs for the signed-in candidate."""

from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from platform_db.models import Company, Job, SkillAliasVersion, SkillConcept
from platform_db.models.job_skills import JobSkill
from pydantic import PostgresDsn
from sqlalchemy import Engine, create_engine, delete, insert

from app.modules.matching.service import MINIMUM_RANKABLE_SKILLS
from app.modules.profiles.models import CandidateProfileSkill

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"
ALIAS_VERSION = "matching.test.1"

PYTHON = UUID("aaaaaaaa-0000-4000-8000-000000000001")
SQL = UUID("aaaaaaaa-0000-4000-8000-000000000002")
CLOUD = UUID("aaaaaaaa-0000-4000-8000-000000000003")
DESIGN = UUID("aaaaaaaa-0000-4000-8000-000000000004")
CONCEPTS = {
    PYTHON: "Python",
    SQL: "SQL",
    CLOUD: "Cloud computing",
    DESIGN: "Product design",
}

# "Everything" asks for exactly what the candidate below has, "Half" for one of
# them plus one they lack, and "Unrelated" for nothing they have.
JOB_SKILLS = {
    "Everything": (PYTHON, SQL, CLOUD),
    "Half": (PYTHON, DESIGN),
    "Unrelated": (DESIGN,),
}


def wipe(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(delete(JobSkill))
        connection.execute(delete(CandidateProfileSkill))
        connection.execute(delete(Job))
        connection.execute(delete(Company))
        connection.execute(delete(SkillConcept).where(SkillConcept.id.in_(CONCEPTS)))
        connection.execute(
            delete(SkillAliasVersion).where(SkillAliasVersion.version == ALIAS_VERSION)
        )


@pytest.fixture
def catalog(database_url: PostgresDsn) -> Iterator[Engine]:
    """Three postings with known skills, cleared around the test."""
    engine = create_engine(str(database_url))
    wipe(engine)

    company_id = uuid4()
    job_ids = {title: uuid4() for title in JOB_SKILLS}
    with engine.begin() as connection:
        connection.execute(insert(SkillAliasVersion), [{"version": ALIAS_VERSION}])
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
                    "id": job_id,
                    "company_id": company_id,
                    "match_key": f"v1:{uuid4().hex}",
                    "title": title,
                    "description": "Work.",
                    "application_url": "https://acme.example.com/apply",
                }
                for title, job_id in job_ids.items()
            ],
        )
        connection.execute(
            insert(JobSkill),
            [
                {
                    "job_id": job_ids[title],
                    "concept_id": concept,
                    "alias_version": ALIAS_VERSION,
                    "surface_form": CONCEPTS[concept],
                }
                for title, concepts in JOB_SKILLS.items()
                for concept in concepts
            ],
        )

    try:
        yield engine
    finally:
        wipe(engine)
        engine.dispose()


@pytest.fixture
def candidate(catalog: Engine, migrated_client: TestClient) -> Callable[..., None]:
    """Sign in, start a profile, and give it the skills a test needs.

    Skills are written directly rather than through the picker, so a test can
    hold a profile too thin for the picker to have produced.
    """

    def arrange(*concepts: UUID, email: str = "candidate@example.com") -> None:
        credentials = {"email": email, "password": PASSWORD}
        assert migrated_client.post("/api/v1/accounts", json=credentials).status_code == 201
        assert migrated_client.post("/api/v1/sessions", json=credentials).status_code == 204
        started = migrated_client.patch("/api/v1/profile", json={"display_name": "Ada"})
        assert started.status_code == 200
        if not concepts:
            return
        with catalog.begin() as connection:
            connection.execute(
                insert(CandidateProfileSkill),
                [
                    {
                        "profile_id": UUID(started.json()["id"]),
                        "concept_id": concept,
                        "vocabulary_version": ALIAS_VERSION,
                    }
                    for concept in concepts
                ],
            )

    return arrange


def matches(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/v1/matches", params=params)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_matches_require_a_session(migrated_client: TestClient) -> None:
    assert migrated_client.get("/api/v1/matches").status_code == 401


def test_the_best_match_is_first_and_says_why(
    migrated_client: TestClient,
    candidate: Callable[..., None],
) -> None:
    candidate(PYTHON, SQL, CLOUD)

    body = matches(migrated_client)

    assert [match["job"]["title"] for match in body["matches"]] == ["Everything", "Half"]
    best = body["matches"][0]
    assert best["score"] == 1.0
    assert [skill["preferred_label"] for skill in best["matched_skills"]] == [
        "Cloud computing",
        "Python",
        "SQL",
    ]
    assert best["missing_skills"] == []


def test_a_partial_match_names_what_the_candidate_lacks(
    migrated_client: TestClient,
    candidate: Callable[..., None],
) -> None:
    candidate(PYTHON, SQL, CLOUD)

    partial = matches(migrated_client)["matches"][1]

    assert partial["job"]["title"] == "Half"
    assert partial["score"] == 0.5
    assert [skill["preferred_label"] for skill in partial["matched_skills"]] == ["Python"]
    assert [skill["preferred_label"] for skill in partial["missing_skills"]] == ["Product design"]


def test_a_posting_sharing_nothing_is_never_ranked(
    migrated_client: TestClient,
    candidate: Callable[..., None],
) -> None:
    """Reading the whole catalogue to score it zero would be a table scan."""
    candidate(PYTHON, SQL, CLOUD)

    body = matches(migrated_client)

    assert "Unrelated" not in [match["job"]["title"] for match in body["matches"]]
    assert body["ranked"] == 2


def test_a_profile_too_thin_to_rank_returns_nothing(
    migrated_client: TestClient,
    candidate: Callable[..., None],
) -> None:
    """Measured: one generic skill produces a confident order worth nothing."""
    candidate(*(PYTHON, SQL, CLOUD)[: MINIMUM_RANKABLE_SKILLS - 1])

    body = matches(migrated_client)

    assert body == {"matches": [], "ranked": 0}


def test_a_profile_with_no_skills_at_all_returns_nothing(
    migrated_client: TestClient,
    candidate: Callable[..., None],
) -> None:
    candidate()

    assert matches(migrated_client) == {"matches": [], "ranked": 0}


def test_the_limit_shortens_the_page_without_hiding_how_many_were_ranked(
    migrated_client: TestClient,
    candidate: Callable[..., None],
) -> None:
    candidate(PYTHON, SQL, CLOUD)

    body = matches(migrated_client, limit=1)

    assert len(body["matches"]) == 1
    assert body["ranked"] == 2


def test_an_unusable_limit_is_refused_rather_than_clamped(
    migrated_client: TestClient,
    candidate: Callable[..., None],
) -> None:
    candidate(PYTHON, SQL, CLOUD)

    assert migrated_client.get("/api/v1/matches", params={"limit": 0}).status_code == 422
    assert migrated_client.get("/api/v1/matches", params={"limit": 500}).status_code == 422
    assert migrated_client.get("/api/v1/matches", params={"page": 2}).status_code == 422


def test_the_same_profile_and_catalogue_rank_the_same_way_every_time(
    migrated_client: TestClient,
    candidate: Callable[..., None],
) -> None:
    candidate(PYTHON, SQL, CLOUD)

    first = matches(migrated_client)
    second = matches(migrated_client)

    assert first == second


def test_a_candidate_reads_only_their_own_matches(
    migrated_client: TestClient,
    candidate: Callable[..., None],
) -> None:
    """There is no identifier to supply, and signing out ends the access."""
    candidate(PYTHON, SQL, CLOUD)
    assert matches(migrated_client)["ranked"] == 2

    assert migrated_client.delete("/api/v1/sessions").status_code == 204

    assert migrated_client.get("/api/v1/matches").status_code == 401
