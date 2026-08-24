import pytest
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}


def register(client: TestClient) -> None:
    assert client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201


def test_login_sets_an_httponly_cookie(migrated_client: TestClient) -> None:
    register(migrated_client)
    response = migrated_client.post("/api/v1/sessions", json=CREDENTIALS)
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "session=" in cookie
    assert "HttpOnly" in cookie
    # Starlette's set_cookie only accepts the lowercase literal ("lax"), which
    # it writes into the header verbatim rather than in the RFC's "Lax" casing
    # -- browsers treat SameSite values case-insensitively either way.
    assert "SameSite=lax" in cookie


def test_the_token_never_appears_in_the_body(migrated_client: TestClient) -> None:
    register(migrated_client)
    response = migrated_client.post("/api/v1/sessions", json=CREDENTIALS)
    assert response.content == b""


def test_a_wrong_password_is_refused(migrated_client: TestClient) -> None:
    register(migrated_client)
    response = migrated_client.post(
        "/api/v1/sessions", json={"email": "ada@example.com", "password": "not the password"}
    )
    assert response.status_code == 401


def test_an_unknown_address_fails_exactly_like_a_wrong_password(
    migrated_client: TestClient,
) -> None:
    register(migrated_client)
    unknown = migrated_client.post(
        "/api/v1/sessions", json={"email": "nobody@example.com", "password": "whatever it is"}
    )
    wrong = migrated_client.post(
        "/api/v1/sessions", json={"email": "ada@example.com", "password": "not the password"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_an_inactive_account_cannot_sign_in(
    migrated_client: TestClient, database_url: PostgresDsn
) -> None:
    register(migrated_client)
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("UPDATE users SET is_active = false"))
    engine.dispose()
    assert migrated_client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 401
