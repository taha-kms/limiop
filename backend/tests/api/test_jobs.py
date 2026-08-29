from collections.abc import Callable
from typing import Any
from uuid import uuid4

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
            "description": "Build reliable data pipelines.\nAnd a second paragraph.",
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
    assert item["excerpt"] == "Build reliable data pipelines. And a second paragraph."


def test_a_listing_never_carries_provenance_or_the_whole_posting(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    """Raw provider payloads have no field to travel in, at any depth."""
    tail = "Everything past the excerpt, which a card has no room for."
    seed_catalog(
        {
            "title": "Listable",
            "description": f"Opening line. {'padding ' * 60}\n{tail}",
            "published_at": at(1),
        }
    )

    body = catalog_client.get("/jobs").text

    assert tail not in body
    assert "raw_payload" not in body
    assert "provenance" not in body
    assert "match_key" not in body


def test_a_long_posting_is_excerpted_rather_than_served_whole(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog({"title": "Verbose", "description": "alpha " * 400, "published_at": at(1)})

    item = catalog_client.get("/jobs").json()["items"][0]

    assert item["excerpt"].endswith("\u2026")
    assert len(item["excerpt"]) < 250


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


def board(key: str, *, name: str | None = None) -> dict[str, Any]:
    """One provenance record, as the seeder wants it."""
    return {
        "key": key,
        "display_name": name or key.title(),
        "source_url": f"https://{key}.example.com/jobs/{uuid4().hex}",
    }


def test_the_source_filter_narrows_to_one_board(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog(
        {"title": "From Greenhouse", "published_at": at(2), "sources": [board("greenhouse")]},
        {"title": "From Arbeitnow", "published_at": at(1), "sources": [board("arbeitnow")]},
    )

    payload = catalog_client.get("/jobs", params={"source": "greenhouse"}).json()

    assert titles(payload) == ["From Greenhouse"]


def test_a_job_both_boards_carry_appears_under_each_and_once_unfiltered(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    """Filtering by a source asks whether it lists the job, not whether it alone does."""
    seed_catalog(
        {
            "title": "Carried twice",
            "published_at": at(2),
            "sources": [board("greenhouse"), board("arbeitnow")],
        },
        {"title": "Carried once", "published_at": at(1), "sources": [board("arbeitnow")]},
    )

    assert titles(catalog_client.get("/jobs", params={"source": "greenhouse"}).json()) == [
        "Carried twice"
    ]
    assert titles(catalog_client.get("/jobs", params={"source": "arbeitnow"}).json()) == [
        "Carried twice",
        "Carried once",
    ]
    assert titles(catalog_client.get("/jobs").json()) == ["Carried twice", "Carried once"]


def test_a_source_filter_composes_and_pages_inside_itself(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog(
        *(
            {
                "title": f"Remote {index}",
                "workplace_type": WorkplaceType.REMOTE,
                "published_at": at(index),
                "sources": [board("greenhouse")],
            }
            for index in range(2)
        ),
        {
            "title": "Remote elsewhere",
            "workplace_type": WorkplaceType.REMOTE,
            "published_at": at(5),
            "sources": [board("arbeitnow")],
        },
        {
            "title": "Onsite here",
            "workplace_type": WorkplaceType.ONSITE,
            "published_at": at(6),
            "sources": [board("greenhouse")],
        },
    )
    narrowed: dict[str, str | int] = {
        "source": "greenhouse",
        "workplace_type": "remote",
        "limit": 1,
    }

    first = catalog_client.get("/jobs", params=narrowed).json()
    second = catalog_client.get(
        "/jobs",
        params={**narrowed, "cursor": first["next_cursor"]},
    ).json()

    assert titles(first) + titles(second) == ["Remote 1", "Remote 0"]
    assert second["next_cursor"] is None


def test_a_source_nothing_ingests_is_refused_rather_than_matching_nothing(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    """An empty page would read as a claim about the board rather than the request."""
    seed_catalog({"title": "Listable", "published_at": at(1), "sources": [board("greenhouse")]})

    response = catalog_client.get("/jobs", params={"source": "greenhous"})

    assert response.status_code == 422
    assert "greenhous" in response.json()["detail"]


def test_the_boards_a_reader_can_filter_by_are_listable(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    seed_catalog(
        {
            "title": "Anywhere",
            "published_at": at(1),
            "sources": [
                board("greenhouse", name="Greenhouse"),
                board("arbeitnow", name="Arbeitnow"),
            ],
        }
    )

    payload = catalog_client.get("/jobs/sources").json()

    assert payload == {
        "sources": [
            {"key": "arbeitnow", "display_name": "Arbeitnow"},
            {"key": "greenhouse", "display_name": "Greenhouse"},
        ]
    }


def test_a_source_listing_carries_no_ingestion_address(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    """Where ingestion reads from is not somewhere a reader would go."""
    seed_catalog({"title": "Anywhere", "published_at": at(1), "sources": [board("greenhouse")]})

    listed = catalog_client.get("/jobs/sources").json()["sources"][0]

    assert set(listed) == {"key", "display_name"}


def test_an_empty_catalog_ingests_no_boards(catalog_client: TestClient) -> None:
    assert catalog_client.get("/jobs/sources").json() == {"sources": []}


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
        pytest.param({"source": ""}, id="empty source"),
        pytest.param({"source": "notaboard"}, id="source no board answers to"),
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
        "source",
    }


def test_the_summary_schema_has_no_path_to_a_description(catalog_client: TestClient) -> None:
    schemas = catalog_client.get("/openapi.json").json()["components"]["schemas"]

    assert "description" not in schemas["JobSummary"]["properties"]
    assert "excerpt" in schemas["JobSummary"]["properties"]


# The frontend types this contract by hand rather than generating it, which is
# only defensible while something fails when the contract moves. Property names
# are not enough: a field turning nullable, or a vocabulary gaining a member,
# breaks a hand-written type without renaming anything.


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        pytest.param(
            "JobSummary",
            {
                "id",
                "company",
                "title",
                "excerpt",
                "location",
                "workplace_type",
                "employment_type",
                "application_url",
                "published_at",
            },
            id="job summary",
        ),
        pytest.param(
            "JobDetail",
            {
                "id",
                "company",
                "title",
                "description",
                "location",
                "workplace_type",
                "employment_type",
                "application_url",
                "published_at",
                "expires_at",
                "status",
                "sources",
            },
            id="job detail",
        ),
        pytest.param("CompanyRead", {"id", "display_name", "website_url"}, id="company"),
        pytest.param("SourceAttribution", {"key", "display_name", "url"}, id="attribution"),
        pytest.param("JobListResponse", {"items", "next_cursor"}, id="listing"),
    ],
)
def test_a_served_schema_carries_exactly_these_fields(
    catalog_client: TestClient,
    schema: str,
    expected: set[str],
) -> None:
    schemas = catalog_client.get("/openapi.json").json()["components"]["schemas"]

    assert set(schemas[schema]["properties"]) == expected


@pytest.mark.parametrize(
    ("schema", "nullable"),
    [
        pytest.param("JobSummary", {"location", "published_at"}, id="job summary"),
        pytest.param("JobDetail", {"location", "published_at", "expires_at"}, id="job detail"),
        pytest.param("CompanyRead", {"website_url"}, id="company"),
        pytest.param("SourceAttribution", set(), id="attribution"),
        pytest.param("JobListResponse", {"next_cursor"}, id="listing"),
    ],
)
def test_exactly_these_fields_may_be_null(
    catalog_client: TestClient,
    schema: str,
    nullable: set[str],
) -> None:
    """Nullability is what the frontend mirrors with a union, so it is contract."""
    properties = catalog_client.get("/openapi.json").json()["components"]["schemas"][schema][
        "properties"
    ]
    accepts_null = {
        name
        for name, definition in properties.items()
        if any(option.get("type") == "null" for option in definition.get("anyOf", ()))
    }

    assert accepts_null == nullable


@pytest.mark.parametrize(
    ("schema", "members"),
    [
        pytest.param(
            "WorkplaceType",
            ["remote", "hybrid", "onsite", "unspecified"],
            id="workplace type",
        ),
        pytest.param(
            "EmploymentType",
            ["full-time", "part-time", "contract", "internship", "temporary", "unspecified"],
            id="employment type",
        ),
        pytest.param("JobStatus", ["active", "expired", "removed"], id="status"),
    ],
)
def test_a_served_vocabulary_carries_exactly_these_members(
    catalog_client: TestClient,
    schema: str,
    members: list[str],
) -> None:
    """A vocabulary gaining a member is the change most likely to slip past.

    Written out rather than read from the domain enum. Comparing the served
    schema against the enum it is generated from cannot fail: a new member
    changes both sides at once. Only a literal list makes the addition stop
    something, which is the point, because a hand-written frontend union does
    not update itself.
    """
    schemas = catalog_client.get("/openapi.json").json()["components"]["schemas"]

    assert schemas[schema]["enum"] == members


def test_the_listing_bounds_its_page_size(catalog_client: TestClient) -> None:
    """The client defaults and caps to these, so they are contract too."""
    parameters = catalog_client.get("/openapi.json").json()["paths"]["/jobs"]["get"]["parameters"]
    limit = next(parameter["schema"] for parameter in parameters if parameter["name"] == "limit")

    assert limit["default"] == DEFAULT_PAGE_SIZE
    assert limit["minimum"] == 1
    assert limit["maximum"] == MAX_PAGE_SIZE


def test_a_known_job_serves_the_detail_contract(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    identifiers = seed_catalog(
        {
            "title": "Senior Data Engineer",
            "company": "Acme GmbH",
            "description": "Build reliable data pipelines.",
            "location": "Berlin",
            "workplace_type": WorkplaceType.REMOTE,
            "employment_type": EmploymentType.FULL_TIME,
            "application_url": "https://acme.example.com/jobs/1",
            "published_at": at(1),
            "sources": [
                {
                    "key": "arbeitnow",
                    "display_name": "Arbeitnow",
                    "source_url": "https://arbeitnow.example.com/jobs/42",
                }
            ],
        }
    )

    response = catalog_client.get(f"/jobs/{identifiers['Senior Data Engineer']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Senior Data Engineer"
    assert payload["description"] == "Build reliable data pipelines."
    assert payload["company"]["display_name"] == "Acme GmbH"
    assert payload["application_url"] == "https://acme.example.com/jobs/1"
    assert payload["status"] == "active"
    assert payload["sources"] == [
        {
            "key": "arbeitnow",
            "display_name": "Arbeitnow",
            "url": "https://arbeitnow.example.com/jobs/42",
        }
    ]


def test_a_job_found_on_several_boards_attributes_all_of_them(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    identifiers = seed_catalog(
        {
            "title": "Listed twice",
            "published_at": at(1),
            "sources": [
                {
                    "key": "arbeitnow",
                    "display_name": "Arbeitnow",
                    "source_url": "https://arbeitnow.example.com/jobs/1",
                },
                {
                    "key": "jobicy",
                    "display_name": "Jobicy",
                    "source_url": "https://jobicy.example.com/jobs/9",
                },
            ],
        }
    )

    payload = catalog_client.get(f"/jobs/{identifiers['Listed twice']}").json()

    assert {source["key"] for source in payload["sources"]} == {"arbeitnow", "jobicy"}


def test_a_job_detail_never_carries_the_raw_provider_record(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    """The payload has no field to travel in, so nothing has to remember to drop it."""
    identifiers = seed_catalog(
        {
            "title": "Listable",
            "published_at": at(1),
            "sources": [
                {
                    "key": "arbeitnow",
                    "display_name": "Arbeitnow",
                    "source_url": "https://arbeitnow.example.com/jobs/1",
                    "source_job_id": "provider-internal-4242",
                    "raw_payload": {"note": "untrusted-provider-prose"},
                }
            ],
        }
    )

    body = catalog_client.get(f"/jobs/{identifiers['Listable']}").text

    assert "untrusted-provider-prose" not in body
    assert "raw_payload" not in body
    assert "provider-internal-4242" not in body
    assert "match_key" not in body


def test_a_job_with_no_recorded_source_still_serves(
    catalog_client: TestClient,
    seed_catalog: Seed,
) -> None:
    identifiers = seed_catalog({"title": "Unattributed", "published_at": at(1)})

    payload = catalog_client.get(f"/jobs/{identifiers['Unattributed']}").json()

    assert payload["sources"] == []


@pytest.mark.parametrize("state", [JobStatus.EXPIRED, JobStatus.REMOVED])
def test_a_lapsed_job_is_served_with_its_status_rather_than_hidden(
    catalog_client: TestClient,
    seed_catalog: Seed,
    state: JobStatus,
) -> None:
    """A saved link is the only route here, so saying the posting closed beats a 404."""
    identifiers = seed_catalog({"title": "Lapsed", "published_at": at(1), "status": state})

    response = catalog_client.get(f"/jobs/{identifiers['Lapsed']}")

    assert response.status_code == 200
    assert response.json()["status"] == state.value
    assert titles(catalog_client.get("/jobs").json()) == []


def test_an_unknown_job_is_not_found(catalog_client: TestClient) -> None:
    response = catalog_client.get(f"/jobs/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "No such job."


def test_an_identifier_that_is_not_a_uuid_is_refused(catalog_client: TestClient) -> None:
    assert catalog_client.get("/jobs/not-a-uuid").status_code == 422


def test_the_detail_endpoint_is_documented(catalog_client: TestClient) -> None:
    openapi = catalog_client.get("/openapi.json").json()

    detail = openapi["paths"]["/jobs/{job_id}"]["get"]
    schema = detail["responses"]["200"]["content"]["application/json"]["schema"]

    assert schema == {"$ref": "#/components/schemas/JobDetail"}
    assert "404" in detail["responses"]


def test_the_detail_schema_has_no_path_to_provenance(catalog_client: TestClient) -> None:
    schemas = catalog_client.get("/openapi.json").json()["components"]["schemas"]

    assert set(schemas["SourceAttribution"]["properties"]) == {"key", "display_name", "url"}
    assert "raw_payload" not in schemas["JobDetail"]["properties"]
    assert "created_at" not in schemas["JobDetail"]["properties"]
