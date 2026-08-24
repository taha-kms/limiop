import pytest
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}


def sign_in(client: TestClient) -> None:
    assert client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    assert client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204


def test_a_signed_in_candidate_is_recognised(migrated_client: TestClient) -> None:
    sign_in(migrated_client)
    response = migrated_client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"


def test_no_cookie_is_unauthorised(migrated_client: TestClient) -> None:
    assert migrated_client.get("/api/v1/me").status_code == 401


def test_a_forged_cookie_is_unauthorised(migrated_client: TestClient) -> None:
    migrated_client.cookies.set("session", "not.a.real.token")
    assert migrated_client.get("/api/v1/me").status_code == 401


def test_bumping_the_version_ends_the_session(
    migrated_client: TestClient, database_url: PostgresDsn
) -> None:
    sign_in(migrated_client)
    assert migrated_client.get("/api/v1/me").status_code == 200
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("UPDATE users SET token_version = token_version + 1"))
    engine.dispose()
    assert migrated_client.get("/api/v1/me").status_code == 401


def test_a_disabled_account_is_refused(
    migrated_client: TestClient, database_url: PostgresDsn
) -> None:
    sign_in(migrated_client)
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("UPDATE users SET is_active = false"))
    engine.dispose()
    assert migrated_client.get("/api/v1/me").status_code == 401
