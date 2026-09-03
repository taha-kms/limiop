import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.contracts import RawPage
from job_ingestion.errors import SourceResponseError
from job_ingestion.pinpoint.provider import PINPOINT, board_request, read_page, stated_company
from job_ingestion.pinpoint.source import DEFAULT_BASE_URL
from tests.boards.fakes import never_sleeps, ok, responding

FIXTURE = Path(__file__).parent / "fixtures" / "postings.json"


def fixture_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(FIXTURE.read_text())
    return body


def test_the_request_names_the_subdomain_on_the_default_host() -> None:
    request = board_request(DEFAULT_BASE_URL, "workwithus", None)

    assert request.url == "https://workwithus.pinpointhq.com/postings.json"


def test_a_configured_base_still_gets_the_subdomain_inserted() -> None:
    request = board_request("https://example.test", "workwithus", None)

    assert request.url == "https://workwithus.example.test/postings.json"


def test_read_page_returns_every_posting_with_no_next_cursor() -> None:
    page = read_page("workwithus", ok(fixture_body()))

    assert len(page.records) == 1
    assert page.next_cursor is None


def test_a_response_with_no_data_array_is_refused() -> None:
    with pytest.raises(SourceResponseError, match="has no data array"):
        read_page("workwithus", ok({}))


def test_stated_company_is_always_none() -> None:
    """The feed never names an employer, so nothing here can confirm a slug."""
    assert stated_company(fixture_body()["data"]) is None


def test_a_board_walk_yields_one_record_stamped_with_its_slug() -> None:
    client = BoardClient(
        PINPOINT,
        BoardConfig(boards=("workwithus",)),
        http_client=responding(ok(fixture_body())),
        sleeper=never_sleeps,
    )

    async def run() -> list[RawPage]:
        return [page async for page in client.fetch_pages()]

    pages = asyncio.run(run())

    assert len(pages) == 1
    assert len(pages[0].records) == 1
    assert pages[0].records[0]["board"] == "workwithus"
    assert client.reached_the_end is True
