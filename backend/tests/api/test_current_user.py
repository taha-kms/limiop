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


def test_a_deleted_account_is_refused(
    migrated_client: TestClient, database_url: PostgresDsn
) -> None:
    """A valid signature naming a row that is simply gone -- the `user is None`
    branch, distinct from `is_active is False` and from a stale `token_version`."""
    sign_in(migrated_client)
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    engine.dispose()
    assert migrated_client.get("/api/v1/me").status_code == 401


def test_every_rejection_looks_the_same(
    migrated_client: TestClient, database_url: PostgresDsn
) -> None:
    """No cookie, a forged one, a stale version, a disabled account, and a
    deleted one must be indistinguishable: a caller learning why a token
    failed learns whether the account exists, which is exactly what a 401
    must not leak."""
    responses = [migrated_client.get("/api/v1/me")]

    migrated_client.cookies.set("session", "not.a.real.token")
    responses.append(migrated_client.get("/api/v1/me"))
    del migrated_client.cookies["session"]

    sign_in(migrated_client)
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("UPDATE users SET token_version = token_version + 1"))
    responses.append(migrated_client.get("/api/v1/me"))

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET token_version = token_version - 1, is_active = false")
        )
    responses.append(migrated_client.get("/api/v1/me"))

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    engine.dispose()
    responses.append(migrated_client.get("/api/v1/me"))

    assert all(response.status_code == 401 for response in responses)
    bodies = [response.json() for response in responses]
    assert all(body == bodies[0] for body in bodies)
