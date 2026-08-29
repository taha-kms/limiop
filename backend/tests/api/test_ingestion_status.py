"""What a person checking on ingestion is told.

Two DAGs run hourly and unattended, and the catalogue they feed cannot be
re-fetched once a posting leaves its board. So these tests are about the
failures being visible, not about the numbers being pretty.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from platform_db.models.ingestion import IngestionRunState

from tests.support.ingestion import ran

SeedRuns = Callable[..., None]

pytestmark = pytest.mark.integration


def reports(client: TestClient) -> dict[str, dict[str, Any]]:
    payload = client.get("/health/ingestion").json()
    return {run["source_key"]: run for run in payload["runs"]}


def test_each_source_is_reported_by_its_most_recent_run(
    catalog_client: TestClient,
    seed_ingestion_runs: SeedRuns,
) -> None:
    seed_ingestion_runs(
        {"source_key": "greenhouse", "started_at": ran(1), "created": 3},
        {"source_key": "greenhouse", "started_at": ran(2), "created": 7},
        {"source_key": "arbeitnow", "started_at": ran(1), "created": 5},
    )

    latest = reports(catalog_client)

    assert set(latest) == {"greenhouse", "arbeitnow"}
    assert latest["greenhouse"]["created"] == 7


def test_a_failed_run_is_reported_as_failed_rather_than_omitted(
    catalog_client: TestClient,
    seed_ingestion_runs: SeedRuns,
) -> None:
    """The whole point. A run nobody watched is the one worth reporting."""
    seed_ingestion_runs(
        {"source_key": "greenhouse", "started_at": ran(1), "created": 7},
        {"source_key": "greenhouse", "started_at": ran(2), "state": IngestionRunState.FAILED},
    )

    report = reports(catalog_client)["greenhouse"]

    assert report["state"] == "failed"
    assert report["finished_at"] is not None


def test_a_run_still_in_flight_is_the_most_recent_one(
    catalog_client: TestClient,
    seed_ingestion_runs: SeedRuns,
) -> None:
    """Otherwise a long run reads as a source that stopped an hour ago."""
    seed_ingestion_runs(
        {"source_key": "greenhouse", "started_at": ran(1)},
        {"source_key": "greenhouse", "started_at": ran(2), "state": IngestionRunState.RUNNING},
    )

    report = reports(catalog_client)["greenhouse"]

    assert report["state"] == "running"
    assert report["finished_at"] is None


def test_a_source_that_never_ran_is_absent_rather_than_healthy(
    catalog_client: TestClient,
    seed_ingestion_runs: SeedRuns,
) -> None:
    """A pipeline nothing has ever seen has nothing to report about it."""
    seed_ingestion_runs({"source_key": "greenhouse", "started_at": ran(1)})

    assert set(reports(catalog_client)) == {"greenhouse"}


def test_no_runs_at_all_reports_nothing(catalog_client: TestClient) -> None:
    response = catalog_client.get("/health/ingestion")

    assert response.status_code == 200
    assert response.json() == {"runs": []}


def test_a_failed_run_does_not_take_the_api_out_of_rotation(
    catalog_client: TestClient,
    seed_ingestion_runs: SeedRuns,
) -> None:
    """A stalled pipeline serves a staler catalogue, not a broken API."""
    seed_ingestion_runs(
        {"source_key": "greenhouse", "started_at": ran(1), "state": IngestionRunState.FAILED}
    )

    assert catalog_client.get("/health/ingestion").status_code == 200
    assert catalog_client.get("/health/ready").status_code == 200


def test_a_report_carries_what_a_reader_needs_and_nothing_else(
    catalog_client: TestClient,
    seed_ingestion_runs: SeedRuns,
) -> None:
    seed_ingestion_runs(
        {
            "source_key": "greenhouse",
            "started_at": ran(1),
            "fetched": 10,
            "created": 4,
            "updated": 3,
            "skipped": 2,
            "failed": 1,
        }
    )

    report = reports(catalog_client)["greenhouse"]

    assert set(report) == {
        "source_key",
        "state",
        "started_at",
        "finished_at",
        "fetched",
        "created",
        "updated",
        "skipped",
        "failed",
    }
    assert report["state"] == "completed"
    assert report["started_at"].startswith("2026-08-01T13:00:00")


def test_the_report_is_documented(catalog_client: TestClient) -> None:
    openapi = catalog_client.get("/openapi.json").json()

    schema = openapi["paths"]["/health/ingestion"]["get"]["responses"]["200"]["content"]

    assert schema["application/json"]["schema"] == {
        "$ref": "#/components/schemas/IngestionStatusResponse"
    }
