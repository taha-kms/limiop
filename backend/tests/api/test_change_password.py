"""Replacing a password.

`end_all_sessions` has always named a password change as one of the three
reasons to invalidate every issued token. Until this route existed it was the
one reason that could never happen, so these tests are mostly about the two
halves of that promise holding at once: everything else signed out, and the
device that did the changing still signed in.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from pydantic import PostgresDsn
from sqlalchemy import create_engine, text

from app.core.config import Environment, Settings
from app.main import create_app

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}
REPLACEMENT = "a different long enough password"


def sign_in(client: TestClient) -> None:
    assert client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    assert client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204


def change(
    client: TestClient,
    current: str = CREDENTIALS["password"],
    new: str = REPLACEMENT,
) -> Response:
    return client.post(
        "/api/v1/me/password",
        json={"current_password": current, "new_password": new},
    )


def test_the_new_password_is_the_one_that_signs_in(migrated_client: TestClient) -> None:
    sign_in(migrated_client)
    assert change(migrated_client).status_code == 204

    assert migrated_client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 401
    accepted = migrated_client.post(
        "/api/v1/sessions",
        json={"email": CREDENTIALS["email"], "password": REPLACEMENT},
    )
    assert accepted.status_code == 204


def test_the_changing_device_stays_signed_in(migrated_client: TestClient) -> None:
    """The cookie the response sets carries the new token version. Issued from
    a version read before the bump, it would be dead on arrival and would sign
    somebody out of the browser they just used."""
    sign_in(migrated_client)
    response = change(migrated_client)

    assert response.status_code == 204
    assert "session=" in response.headers["set-cookie"]
    assert migrated_client.get("/api/v1/me").status_code == 200


def test_every_other_device_is_signed_out(migrated_client: TestClient) -> None:
    sign_in(migrated_client)
    other = TestClient(migrated_client.app)
    assert other.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204

    assert change(migrated_client).status_code == 204

    # The other device holds a valid, unexpired token. What stops it is the
    # version bump, which is the whole reason a password change ends sessions.
    assert other.get("/api/v1/me").status_code == 401


def test_the_current_password_has_to_be_right(migrated_client: TestClient) -> None:
    sign_in(migrated_client)
    refused = change(migrated_client, current="not the password at all")

    assert refused.status_code == 403
    # Nothing moved: the old password still signs in, so the account was not
    # left in a state where neither password works.
    assert migrated_client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204


def test_a_short_new_password_is_refused(migrated_client: TestClient) -> None:
    sign_in(migrated_client)
    assert change(migrated_client, new="too short").status_code == 422


def test_changing_a_password_needs_a_session(migrated_client: TestClient) -> None:
    assert change(migrated_client).status_code == 401


@pytest.fixture
def throttled_client(database_url: PostgresDsn) -> Iterator[TestClient]:
    """A client that gets two attempts, so a test can spend them."""
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    application = create_app(
        Settings(
            environment=Environment.TEST,
            database_url=database_url,
            auth_attempts=2,
            auth_attempt_window_seconds=60.0,
        )
    )
    with TestClient(application) as client:
        yield client
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    engine.dispose()


def test_repeated_wrong_current_passwords_are_refused(throttled_client: TestClient) -> None:
    """Two argon2 hashes a request makes this the most expensive authenticated
    route in the API, so the ceiling matters more here than where it started."""
    sign_in(throttled_client)

    assert change(throttled_client, current="wrong once").status_code == 403
    assert change(throttled_client, current="wrong twice").status_code == 403
    refused = change(throttled_client, current="wrong again")

    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) > 0


def test_a_successful_change_does_not_spend_an_attempt(throttled_client: TestClient) -> None:
    """Only failures count, so somebody who types their own password correctly
    never runs out of room to change it."""
    sign_in(throttled_client)

    for _ in range(3):
        assert change(throttled_client, current=CREDENTIALS["password"]).status_code == 204
        assert (
            change(throttled_client, current=REPLACEMENT, new=CREDENTIALS["password"]).status_code
            == 204
        )
