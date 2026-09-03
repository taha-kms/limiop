import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.contracts import RawPage
from job_ingestion.errors import SourceResponseError
from job_ingestion.polymer.provider import POLYMER, board_request, detail_request, read_page
from job_ingestion.polymer.source import DEFAULT_BASE_URL
from tests.boards.fakes import never_sleeps, ok, routing

LIST_FIXTURE = Path(__file__).parent / "fixtures" / "list.json"
DETAIL_FIXTURE = Path(__file__).parent / "fixtures" / "detail.json"


def list_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(LIST_FIXTURE.read_text())
    return body


def detail_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(DETAIL_FIXTURE.read_text())
    return body


def test_the_first_page_is_requested_by_number() -> None:
    request = board_request(DEFAULT_BASE_URL, "aperturelabs", None)

    assert request.url == f"{DEFAULT_BASE_URL}/aperturelabs/jobs"
    assert dict(request.params) == {"page": "1"}


def test_a_later_page_is_requested_by_its_cursor() -> None:
    request = board_request(DEFAULT_BASE_URL, "aperturelabs", 3)

    assert dict(request.params) == {"page": "3"}


def test_read_page_returns_the_next_cursor_from_meta() -> None:
    body = {
        "items": [{"id": 1, "title": "Engineer", "organization_name": "Acme"}],
        "meta": {"next_page": 2},
    }
    page = read_page("acme", ok(body))

    assert len(page.records) == 1
    assert page.next_cursor == 2


def test_an_empty_page_past_the_end_stops_the_walk() -> None:
    """A request past the last page still advertises a next page."""
    body = {"items": [], "meta": {"next_page": 4}}
    page = read_page("acme", ok(body))

    assert page.records == ()
    assert page.next_cursor is None


def test_the_last_page_has_no_next_cursor() -> None:
    page = read_page("aperturelabs", ok(list_body()))

    assert len(page.records) == 1
    assert page.next_cursor is None


def test_a_response_with_no_items_array_is_refused() -> None:
    body = {"meta": {"next_page": None}}

    with pytest.raises(SourceResponseError, match="has no items array"):
        read_page("acme", ok(body))


def test_stated_company_reads_the_first_non_blank_name() -> None:
    records = [{"organization_name": ""}, {"organization_name": "Aperture Labs"}]

    assert POLYMER.stated_company(records) == "Aperture Labs"


def test_stated_company_with_no_records_states_nothing() -> None:
    assert POLYMER.stated_company([]) is None


def test_detail_request_names_the_second_call() -> None:
    request = detail_request({"board": "aperturelabs", "id": 30084})

    assert request is not None
    assert request.url == f"{DEFAULT_BASE_URL}/aperturelabs/jobs/30084"


def test_detail_request_for_a_record_without_a_usable_id_asks_nothing() -> None:
    assert detail_request({"board": "aperturelabs", "id": "not-an-int"}) is None
    assert detail_request({"id": 30084}) is None


def walk() -> RawPage:
    client = BoardClient(
        POLYMER,
        BoardConfig(boards=("aperturelabs",)),
        http_client=routing(
            {
                "/v1/hire/organizations/aperturelabs/jobs": ok(list_body()),
                "/v1/hire/organizations/aperturelabs/jobs/30084": ok(detail_body()),
            }
        ),
        sleeper=never_sleeps,
    )
    return asyncio.run(client.fetch_board("aperturelabs"))


def test_a_board_walk_yields_one_hydrated_record() -> None:
    page = walk()

    assert len(page.records) == 1
    record = page.records[0]
    assert record["board"] == "aperturelabs"
    assert record["id"] == 30084
    assert record["description"]
