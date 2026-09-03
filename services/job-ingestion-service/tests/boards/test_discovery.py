import asyncio
from typing import Any

import httpx2

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.discovery import DiscoveryOutcome, discover
from job_ingestion.boards.provider import BoardProvider
from tests.boards.fakes import json_provider, never_sleeps, ok, responding, xml_provider


def board(company: str, count: int = 1) -> httpx2.Response:
    return ok(
        {"jobs": [{"id": index, "title": "Engineer", "company": company} for index in range(count)]}
    )


def client(
    *replies: httpx2.Response | Exception, provider: BoardProvider[Any] | None = None
) -> BoardClient:
    return BoardClient(
        provider if provider is not None else json_provider(),
        BoardConfig(boards=(), retry_backoff_seconds=0.0),
        http_client=responding(*replies),
        sleeper=never_sleeps,
    )


def run(fetcher: BoardClient, company: str) -> Any:
    return asyncio.run(discover(fetcher, company))


def test_the_provider_says_whose_board_answered() -> None:
    result = run(client(board("Acme")), "Acme GmbH")

    assert result.outcome is DiscoveryOutcome.CONFIRMED
    assert result.slug == "acme"
    assert result.found_company == "Acme"


def test_a_board_stating_somebody_else_is_rejected() -> None:
    result = run(client(board("Globex"), board("Globex"), board("Globex")), "Acme")

    assert result.outcome is DiscoveryOutcome.WRONG_COMPANY
    assert result.found_company == "Globex"


def test_a_feed_that_never_states_a_company_is_unverifiable() -> None:
    """A board answered. Nothing says whose, so nothing is confirmed."""
    body = b"<feed><position><id>1</id><title>One</title></position></feed>"
    fetcher = client(httpx2.Response(200, content=body), provider=xml_provider())

    result = run(fetcher, "Acme")

    assert result.outcome is DiscoveryOutcome.UNVERIFIABLE
    assert result.slug == "acme"
    assert result.found_company is None


def test_an_unverifiable_board_stops_the_search() -> None:
    """Every later guess would be as unverifiable, and each costs a request."""
    body = b"<feed><position><id>1</id><title>One</title></position></feed>"
    fetcher = client(httpx2.Response(200, content=body), provider=xml_provider())

    result = run(fetcher, "Acme Health Group")

    assert result.outcome is DiscoveryOutcome.UNVERIFIABLE
    assert result.slug == "acmehealthgroup"


def test_an_empty_board_confirms_nothing() -> None:
    result = run(client(ok({"jobs": []}), ok({"jobs": []}), ok({"jobs": []})), "Acme Health Group")

    assert result.outcome is DiscoveryOutcome.NOT_FOUND
