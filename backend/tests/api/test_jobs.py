from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.modules.jobs.domain import EmploymentType, JobStatus, WorkplaceType
from app.modules.jobs.queries import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from tests.support.catalog import at

Seed = Callable[..., dict[str, Any]]

pytestmark = pytest.mark.integration


def titles(payload: dict[str, Any]) -> list[str]:
    return [item["title"] for item in payload["items"]]


def test_an_empty_catalog_returns_an_empty_batch(catalog_client: TestClient) -> None:
    response = catalog_client.get("/jobs")

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


def test_jobs_are_returned_newest_first(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog(
        {"title": "Older", "published_at": at(1)},
        {"title": "Newest", "published_at": at(3)},
        {"title": "Middle", "published_at": at(2)},
    )

    payload = catalog_client.get("/jobs").json()

    assert titles(payload) == ["Newest", "Middle", "Older"]
    assert payload["next_cursor"] is None


def test_a_listed_job_carries_what_a_card_needs(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog(
        {
            "title": "Senior Data Engineer",
            "company": "Acme GmbH",
            "location": "Berlin",
            "workplace_type": WorkplaceType.REMOTE,
            "employment_type": EmploymentType.FULL_TIME,
            "application_url": "https://acme.example.com/jobs/1",
            "published_at": at(1),
        }
    )

    item = catalog_client.get("/jobs").json()["items"][0]

    assert item["title"] == "Senior Data Engineer"
    assert item["company"]["display_name"] == "Acme GmbH"
    assert item["location"] == "Berlin"
    assert item["workplace_type"] == "remote"
    assert item["employment_type"] == "full-time"
    assert item["application_url"] == "https://acme.example.com/jobs/1"
    assert item["published_at"] is not None


def test_a_listing_never_carries_provenance_or_prose(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    """Raw provider payloads have no field to travel in, at any depth."""
    seed_catalog({"title": "Listable", "description": "Secret prose.", "published_at": at(1)})

    body = catalog_client.get("/jobs").text

    assert "Secret prose." not in body
    assert "raw_payload" not in body
    assert "provenance" not in body
    assert "fingerprint" not in body


def test_only_active_jobs_are_served(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog(
        {"title": "Listable", "published_at": at(1)},
        {"title": "Expired", "published_at": at(2), "status": JobStatus.EXPIRED},
        {"title": "Removed", "published_at": at(3), "status": JobStatus.REMOVED},
    )

    assert titles(catalog_client.get("/jobs").json()) == ["Listable"]


def test_a_client_pages_through_the_catalog_with_the_returned_cursor(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog(*({"title": f"Job {index}", "published_at": at(index)} for index in range(5)))

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params: dict[str, Any] = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        payload = catalog_client.get("/jobs", params=params).json()
        seen.extend(titles(payload))
        cursor = payload["next_cursor"]
        if cursor is None:
            break

    assert seen == [f"Job {index}" for index in reversed(range(5))]


def test_the_default_batch_is_twenty(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog(*({"title": f"Job {index:02d}", "published_at": at(index)} for index in range(25)))

    payload = catalog_client.get("/jobs").json()

    assert len(payload["items"]) == DEFAULT_PAGE_SIZE
    assert payload["next_cursor"] is not None


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        pytest.param(
            {"location": "berlin"},
            ["Remote Berlin", "Hybrid Berlin"],
            id="location",
        ),
        pytest.param({"workplace_type": "onsite"}, ["Onsite Munich"], id="workplace type"),
        pytest.param({"employment_type": "internship"}, ["Placement"], id="employment type"),
        pytest.param({"q": "remote"}, ["Remote Berlin"], id="title search"),
        pytest.param(
            {"workplace_type": ["remote", "hybrid"]},
            ["Remote Berlin", "Hybrid Berlin"],
            id="repeated workplace type",
        ),
        pytest.param(
            {"location": "berlin", "workplace_type": "remote"},
            ["Remote Berlin"],
            id="combined",
        ),
    ],
)
def test_filters_narrow_the_listing(
    catalog_client: TestClient,
    seed_catalog: Seed,
    params: dict[str, Any],
    expected: list[str],
) -> None:
    seed_catalog(
        {
            "title": "Remote Berlin",
            "location": "Berlin, Germany",
            "workplace_type": WorkplaceType.REMOTE,
            "published_at": at(4),
        },
        {
            "title": "Hybrid Berlin",
            "location": "Berlin, Germany",
            "workplace_type": WorkplaceType.HYBRID,
            "published_at": at(3),
        },
        {
            "title": "Onsite Munich",
            "location": "Munich, Germany",
            "workplace_type": WorkplaceType.ONSITE,
            "published_at": at(2),
        },
        {
            "title": "Placement",
            "location": "Hamburg",
            "employment_type": EmploymentType.INTERNSHIP,
            "published_at": at(1),
        },
    )

    payload = catalog_client.get("/jobs", params=params).json()

    assert titles(payload) == expected


def test_the_company_filter_narrows_to_one_employer(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog(
        {"title": "At Acme", "company": "Acme GmbH", "published_at": at(2)},
        {"title": "At Globex", "company": "Globex AG", "published_at": at(1)},
    )

    listed = catalog_client.get("/jobs").json()["items"]
    acme = next(item for item in listed if item["title"] == "At Acme")

    payload = catalog_client.get("/jobs", params={"company_id": acme["company"]["id"]}).json()

    assert titles(payload) == ["At Acme"]


def test_paging_a_filtered_listing_stays_inside_the_filter(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog(
        *(
            {
                "title": f"Engineer {index}",
                "workplace_type": WorkplaceType.REMOTE,
                "published_at": at(index),
            }
            for index in range(3)
        ),
        *(
            {
                "title": f"Designer {index}",
                "workplace_type": WorkplaceType.ONSITE,
                "published_at": at(index + 10),
            }
            for index in range(3)
        ),
    )

    first = catalog_client.get("/jobs", params={"limit": 2, "workplace_type": "remote"}).json()
    second = catalog_client.get(
        "/jobs",
        params={"limit": 2, "workplace_type": "remote", "cursor": first["next_cursor"]},
    ).json()

    assert titles(first) + titles(second) == ["Engineer 2", "Engineer 1", "Engineer 0"]


def test_an_unreadable_cursor_is_a_client_error(catalog_client: TestClient) -> None:
    response = catalog_client.get("/jobs", params={"cursor": "not-a-cursor!"})

    assert response.status_code == 400
    assert "cursor" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"limit": 0}, id="page below one"),
        pytest.param({"limit": MAX_PAGE_SIZE + 1}, id="page above the ceiling"),
        pytest.param({"limit": "many"}, id="page that is not a number"),
        pytest.param({"company_id": "not-a-uuid"}, id="identifier that is not a uuid"),
        pytest.param({"workplace_type": "underwater"}, id="value outside the vocabulary"),
        pytest.param({"employment_type": "eternal"}, id="relationship outside the vocabulary"),
        pytest.param({"q": ""}, id="empty search term"),
        pytest.param({"location": ""}, id="empty location"),
        pytest.param({"q": "x" * 500}, id="search term beyond the bound"),
    ],
)
def test_an_invalid_request_is_refused(
    catalog_client: TestClient,
    params: dict[str, Any],
) -> None:
    assert catalog_client.get("/jobs", params=params).status_code == 422


def test_an_unknown_filter_is_refused_rather_than_ignored(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    """A dropped typo would return the whole catalog and look like a match."""
    seed_catalog({"title": "Listable", "published_at": at(1)})

    response = catalog_client.get("/jobs", params={"workplace_typ": "remote"})

    assert response.status_code == 422


def test_the_listing_is_documented(catalog_client: TestClient) -> None:
    openapi = catalog_client.get("/openapi.json").json()

    listing = openapi["paths"]["/jobs"]["get"]
    schema = listing["responses"]["200"]["content"]["application/json"]["schema"]

    assert schema == {"$ref": "#/components/schemas/JobListResponse"}
    assert "400" in listing["responses"]
    assert {parameter["name"] for parameter in listing["parameters"]} == {
        "cursor",
        "limit",
        "company_id",
        "location",
        "workplace_type",
        "employment_type",
        "q",
    }


def test_the_summary_schema_has_no_path_to_a_description(catalog_client: TestClient) -> None:
    schemas = catalog_client.get("/openapi.json").json()["components"]["schemas"]

    assert "description" not in schemas["JobSummary"]["properties"]
