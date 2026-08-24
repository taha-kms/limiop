import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "Ada@Example.com", "password": "correct horse battery staple"}


def test_registration_returns_the_account_without_credentials(
    migrated_client: TestClient,
) -> None:
    response = migrated_client.post("/api/v1/accounts", json=CREDENTIALS)
    assert response.status_code == 201
    body = response.json()
    # EmailStr (via email-validator) normalizes the domain to lowercase as
    # part of parsing the request, before this handler ever sees the value —
    # the local part's casing survives, the domain's does not.
    assert body["email"] == "Ada@example.com"
    assert "id" in body
    assert "password" not in body
    assert "password_hash" not in body


def test_the_same_address_cannot_register_twice(migrated_client: TestClient) -> None:
    assert migrated_client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    again = migrated_client.post(
        "/api/v1/accounts", json={"email": "ada@example.COM", "password": "another one entirely"}
    )
    assert again.status_code == 409
    assert "password" not in again.text


def test_a_short_password_is_refused(migrated_client: TestClient) -> None:
    response = migrated_client.post(
        "/api/v1/accounts", json={"email": "grace@example.com", "password": "short"}
    )
    assert response.status_code == 422
