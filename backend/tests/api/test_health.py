from fastapi.testclient import TestClient


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_has_documented_response(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()

    response_schema = openapi["paths"]["/health"]["get"]["responses"]["200"]["content"]
    assert response_schema["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HealthResponse"
    }
