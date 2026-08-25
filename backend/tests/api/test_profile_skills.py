from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import create_engine, delete, insert

from app.modules.profiles import service as profile_service
from app.modules.profiles.models import CandidateProfileSkill
from app.modules.skills.models import SkillConcept
from app.modules.skills.resolution import AliasTableDocument, KnownSkillResolver

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"
POSTGRES_ID = UUID("a487a42c-feba-42ef-bcbd-a793f0188627")
ILLUSTRATOR_ID = UUID("8cb94723-c872-47d2-883b-cb7c4201849b")
ARTIFICIAL_INTELLIGENCE_ID = UUID("b628ff48-9ed3-426d-8d3f-a17f18b71f50")


def resolver_document() -> AliasTableDocument:
    return AliasTableDocument.model_validate(
        {
            "schema_version": 1,
            "vocabulary_version": "profile.test.1",
            "concepts": [
                {"id": POSTGRES_ID, "preferred_label": "PostgreSQL"},
                {"id": ILLUSTRATOR_ID, "preferred_label": "Adobe Illustrator"},
                {
                    "id": ARTIFICIAL_INTELLIGENCE_ID,
                    "preferred_label": "Artificial intelligence",
                },
            ],
            "surface_forms": [
                {"surface_form": "Postgres", "concept_ids": [POSTGRES_ID]},
                {
                    "surface_form": "AI",
                    "concept_ids": [ILLUSTRATOR_ID, ARTIFICIAL_INTELLIGENCE_ID],
                },
            ],
        }
    )


@pytest.fixture
def profile_skill_catalog(
    database_url: PostgresDsn,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[KnownSkillResolver]:
    resolver = KnownSkillResolver(resolver_document())
    engine = create_engine(str(database_url))
    concept_ids = [POSTGRES_ID, ILLUSTRATOR_ID, ARTIFICIAL_INTELLIGENCE_ID]
    with engine.begin() as connection:
        connection.execute(
            delete(CandidateProfileSkill).where(CandidateProfileSkill.concept_id.in_(concept_ids))
        )
        connection.execute(delete(SkillConcept).where(SkillConcept.id.in_(concept_ids)))
        connection.execute(
            insert(SkillConcept),
            [
                {"id": POSTGRES_ID, "preferred_label": "PostgreSQL"},
                {"id": ILLUSTRATOR_ID, "preferred_label": "Adobe Illustrator"},
                {
                    "id": ARTIFICIAL_INTELLIGENCE_ID,
                    "preferred_label": "Artificial intelligence",
                },
            ],
        )
    monkeypatch.setattr(profile_service, "load_default_resolver", lambda: resolver)
    try:
        yield resolver
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(CandidateProfileSkill).where(
                    CandidateProfileSkill.concept_id.in_(concept_ids)
                )
            )
            connection.execute(delete(SkillConcept).where(SkillConcept.id.in_(concept_ids)))
        engine.dispose()


def register_and_sign_in(client: TestClient, email: str) -> None:
    credentials = {"email": email, "password": PASSWORD}
    assert client.post("/api/v1/accounts", json=credentials).status_code == 201
    assert client.post("/api/v1/sessions", json=credentials).status_code == 204


def start_profile(client: TestClient) -> None:
    assert client.patch("/api/v1/profile", json={"display_name": "Ada"}).status_code == 200


def test_profile_skill_endpoints_require_authentication(migrated_client: TestClient) -> None:
    assert migrated_client.get("/api/v1/profile/skills").status_code == 401
    assert (
        migrated_client.post("/api/v1/profile/skills", json={"term": "Postgres"}).status_code == 401
    )
    assert migrated_client.delete(f"/api/v1/profile/skills/{POSTGRES_ID}").status_code == 401


def test_profile_must_exist_before_its_skills_can_be_changed(
    migrated_client: TestClient,
    profile_skill_catalog: KnownSkillResolver,
) -> None:
    register_and_sign_in(migrated_client, "missing-profile@example.com")

    assert migrated_client.get("/api/v1/profile/skills").status_code == 404
    assert (
        migrated_client.post("/api/v1/profile/skills", json={"term": "Postgres"}).status_code == 404
    )
    assert migrated_client.delete(f"/api/v1/profile/skills/{POSTGRES_ID}").status_code == 404


def test_add_list_and_remove_a_resolved_skill_idempotently(
    migrated_client: TestClient,
    profile_skill_catalog: KnownSkillResolver,
) -> None:
    register_and_sign_in(migrated_client, "skills@example.com")
    start_profile(migrated_client)

    first = migrated_client.post("/api/v1/profile/skills", json={"term": "Postgres"})
    duplicate = migrated_client.post("/api/v1/profile/skills", json={"term": "POSTGRES!"})

    assert first.status_code == duplicate.status_code == 201
    assert first.json() == duplicate.json()
    assert first.json()["concept_id"] == str(POSTGRES_ID)
    assert first.json()["preferred_label"] == "PostgreSQL"
    assert first.json()["vocabulary_version"] == "profile.test.1"

    listed = migrated_client.get("/api/v1/profile/skills")
    assert listed.status_code == 200
    assert listed.json() == [first.json()]

    assert migrated_client.delete(f"/api/v1/profile/skills/{POSTGRES_ID}").status_code == 204
    assert migrated_client.get("/api/v1/profile/skills").json() == []
    assert migrated_client.delete(f"/api/v1/profile/skills/{POSTGRES_ID}").status_code == 404


@pytest.mark.parametrize(
    ("term", "code", "message_fragment"),
    [
        ("AI", "ambiguous_skill", "ambiguous"),
        ("quantum widget orchestration", "unknown_skill", "not in the canonical vocabulary"),
    ],
)
def test_nonselectable_terms_are_visibly_refused_and_not_stored(
    migrated_client: TestClient,
    profile_skill_catalog: KnownSkillResolver,
    term: str,
    code: str,
    message_fragment: str,
) -> None:
    register_and_sign_in(migrated_client, f"{code}@example.com")
    start_profile(migrated_client)

    response = migrated_client.post("/api/v1/profile/skills", json={"term": term})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code
    assert message_fragment in response.json()["detail"]["message"]
    assert migrated_client.get("/api/v1/profile/skills").json() == []


def test_skill_routes_are_scoped_to_the_signed_in_owner(
    migrated_client: TestClient,
    profile_skill_catalog: KnownSkillResolver,
) -> None:
    register_and_sign_in(migrated_client, "first-owner@example.com")
    start_profile(migrated_client)
    assert (
        migrated_client.post("/api/v1/profile/skills", json={"term": "Postgres"}).status_code == 201
    )

    other = TestClient(migrated_client.app)
    register_and_sign_in(other, "second-owner@example.com")
    start_profile(other)

    assert other.get("/api/v1/profile/skills").json() == []
    assert other.delete(f"/api/v1/profile/skills/{POSTGRES_ID}").status_code == 404
    assert len(migrated_client.get("/api/v1/profile/skills").json()) == 1


def test_a_resolved_concept_missing_from_the_database_is_reported(
    migrated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = KnownSkillResolver(resolver_document())
    monkeypatch.setattr(profile_service, "load_default_resolver", lambda: resolver)
    register_and_sign_in(migrated_client, "catalog-mismatch@example.com")
    start_profile(migrated_client)

    response = migrated_client.post("/api/v1/profile/skills", json={"term": "Postgres"})

    assert response.status_code == 503
    assert response.json()["detail"] == "the canonical skill catalog is unavailable"


@pytest.mark.parametrize("payload", [{}, {"term": "   "}, {"term": "Postgres", "extra": True}])
def test_invalid_skill_selection_requests_are_rejected(
    migrated_client: TestClient,
    payload: dict[str, object],
) -> None:
    register_and_sign_in(migrated_client, f"invalid-{len(payload)}@example.com")
    start_profile(migrated_client)

    assert migrated_client.post("/api/v1/profile/skills", json=payload).status_code == 422
