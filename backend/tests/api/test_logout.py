import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}


def sign_in(client: TestClient) -> None:
    assert client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    assert client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204


def test_logging_out_clears_the_cookie(migrated_client: TestClient) -> None:
    sign_in(migrated_client)
    response = migrated_client.delete("/api/v1/sessions")
    assert response.status_code == 204
    # The delete has to match the attributes login set (name and path) or the
    # browser keeps the original cookie instead of overwriting it.
    cookie = response.headers["set-cookie"]
    assert "session=" in cookie
    assert "Path=/" in cookie
    assert migrated_client.get("/api/v1/me").status_code == 401


def test_logging_out_here_leaves_another_device_signed_in(
    migrated_client: TestClient,
) -> None:
    """A second client stands in for a second device: same account, own cookie."""
    sign_in(migrated_client)
    other = TestClient(migrated_client.app)
    assert other.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204
    assert migrated_client.delete("/api/v1/sessions").status_code == 204
    assert other.get("/api/v1/me").status_code == 200


def test_logging_out_everywhere_ends_the_other_device_too(
    migrated_client: TestClient,
) -> None:
    sign_in(migrated_client)
    other = TestClient(migrated_client.app)
    assert other.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204
    response = migrated_client.delete("/api/v1/sessions/all")
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "session=" in cookie
    assert "Path=/" in cookie
    # Not merely a 204 from this device: the other device's own cookie is
    # rejected too, which is what a version bump -- not a cookie clear -- buys.
    assert other.get("/api/v1/me").status_code == 401


def test_logging_out_everywhere_needs_a_session(migrated_client: TestClient) -> None:
    assert migrated_client.delete("/api/v1/sessions/all").status_code == 401
