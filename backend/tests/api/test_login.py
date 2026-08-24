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


def test_login_pins_secure_max_age_and_path_on_the_cookie(
    production_like_client: TestClient,
) -> None:
    """`migrated_client` runs under `Environment.TEST`, where `Secure` is off
    by design -- these three attributes only show up under an environment
    where the cookie is meant to be handled the way production will."""
    register(production_like_client)
    response = production_like_client.post("/api/v1/sessions", json=CREDENTIALS)
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie
    assert "Max-Age=3600" in cookie
    assert "Path=/" in cookie


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
    assert "set-cookie" not in response.headers


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
    assert "set-cookie" not in unknown.headers
    assert "set-cookie" not in wrong.headers


def test_an_inactive_account_cannot_sign_in(
    migrated_client: TestClient, database_url: PostgresDsn
) -> None:
    register(migrated_client)
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("UPDATE users SET is_active = false"))
    engine.dispose()
    response = migrated_client.post("/api/v1/sessions", json=CREDENTIALS)
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
