import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}


def sign_in(client: TestClient) -> None:
    assert client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    assert client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204


def test_profile_requires_a_signed_in_candidate(migrated_client: TestClient) -> None:
    assert migrated_client.get("/api/v1/profile").status_code == 401
    assert migrated_client.patch("/api/v1/profile", json={"display_name": "Ada"}).status_code == 401


def test_a_profile_that_has_not_started_is_missing(migrated_client: TestClient) -> None:
    sign_in(migrated_client)

    response = migrated_client.get("/api/v1/profile")

    assert response.status_code == 404


def test_partial_steps_survive_leaving_and_returning(migrated_client: TestClient) -> None:
    sign_in(migrated_client)

    first = migrated_client.patch("/api/v1/profile", json={"display_name": "  Ada  "})
    assert first.status_code == 200
    assert first.json()["display_name"] == "Ada"
    assert first.json()["profile_complete"] is False

    returned = migrated_client.get("/api/v1/profile")
    assert returned.status_code == 200
    assert returned.json()["display_name"] == "Ada"
    assert returned.json()["location"] is None

    second = migrated_client.patch("/api/v1/profile", json={"location": "London"})
    assert second.status_code == 200
    assert second.json()["display_name"] == "Ada"
    assert second.json()["location"] == "London"
    assert second.json()["profile_complete"] is False


def test_manual_steps_reach_the_same_complete_profile_shape(
    migrated_client: TestClient,
) -> None:
    sign_in(migrated_client)
    assert migrated_client.patch("/api/v1/profile", json={"display_name": "Ada"}).status_code == 200
    assert migrated_client.patch("/api/v1/profile", json={"location": "London"}).status_code == 200

    response = migrated_client.patch(
        "/api/v1/profile",
        json={
            "workplace_types": ["hybrid", "remote"],
            "employment_types": ["full-time"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile_complete"] is True
    assert body["workplace_types"] == ["hybrid", "remote"]
    assert body["employment_types"] == ["full-time"]
    assert set(body) == {
        "id",
        "display_name",
        "location",
        "workplace_types",
        "employment_types",
        "headline",
        "summary",
        "years_experience",
        "profile_complete",
        "created_at",
        "updated_at",
    }


def test_optional_profile_fields_are_saved_without_gating_completeness(
    migrated_client: TestClient,
) -> None:
    sign_in(migrated_client)

    response = migrated_client.patch(
        "/api/v1/profile",
        json={
            "headline": "Analytical engine programmer",
            "summary": "Builds reliable systems.",
            "years_experience": 4,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["headline"] == "Analytical engine programmer"
    assert body["summary"] == "Builds reliable systems."
    assert body["years_experience"] == 4
    assert body["profile_complete"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"display_name": "   "},
        {"location": None},
        {"workplace_types": []},
        {"employment_types": ["full-time", "full-time"]},
        {"headline": "First line\nsecond line"},
        {"years_experience": -1},
        {"unknown": "field"},
    ],
)
def test_invalid_profile_steps_are_rejected(
    migrated_client: TestClient, payload: dict[str, object]
) -> None:
    sign_in(migrated_client)

    response = migrated_client.patch("/api/v1/profile", json=payload)

    assert response.status_code == 422
