from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import create_engine, text

from app.core.config import Environment, Settings
from app.modules.accounts.tokens import SessionClaims, issue_token

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}

# Long enough that PyJWT does not warn about the key length while forging.
ATTACKERS_SECRET = "a-secret-the-server-has-never-seen"


def sign_in(client: TestClient) -> None:
    assert client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    assert client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204


def sign(claims: SessionClaims, secret: str) -> str:
    return issue_token(claims, secret=secret, lifetime_minutes=60, now=datetime.now(UTC))


def stored_claims(database_url: PostgresDsn) -> SessionClaims:
    """The claims the server would accept, read straight out of the row."""
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        row = connection.execute(text("SELECT id, token_version FROM users")).one()
    engine.dispose()
    return SessionClaims(user_id=UUID(str(row[0])), token_version=int(row[1]))


def test_a_signed_in_candidate_is_recognised(migrated_client: TestClient) -> None:
    sign_in(migrated_client)
    response = migrated_client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"


def test_no_cookie_is_unauthorised(migrated_client: TestClient) -> None:
    assert migrated_client.get("/api/v1/me").status_code == 401


def test_a_forged_cookie_is_unauthorised(
    migrated_client: TestClient, database_url: PostgresDsn
) -> None:
    """Signature rejection through the HTTP path.

    A token has to be structurally valid to get as far as the signature check
    -- a string that fails base64 decoding is thrown out by the parser first,
    which would leave the signature untested no matter what the test is
    called. So these are the claims the server would accept for a live
    account, at a live expiry, differing from a real cookie in the signing key
    and nothing else. The authentic control is asserted alongside it, or a
    server that had stopped verifying signatures altogether would still look
    like a pass.
    """
    sign_in(migrated_client)
    claims = stored_claims(database_url)

    migrated_client.cookies.set("session", sign(claims, ATTACKERS_SECRET))
    assert migrated_client.get("/api/v1/me").status_code == 401

    authentic = Settings(environment=Environment.TEST).session_secret
    migrated_client.cookies.set("session", sign(claims, authentic))
    assert migrated_client.get("/api/v1/me").status_code == 200


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

    forged = sign(SessionClaims(user_id=uuid4(), token_version=0), ATTACKERS_SECRET)
    migrated_client.cookies.set("session", forged)
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
