"""Finding a Pinpoint board without anyone typing its slug.

The feed never states whose postings a board carries, so a guess that answers
is the whole story: it cannot be confirmed, only reported as unverifiable.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx2

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.discovery import DiscoveryOutcome, discover
from job_ingestion.pinpoint.provider import PINPOINT
from tests.boards.fakes import never_sleeps, ok, routing

FIXTURE = Path(__file__).parent / "fixtures" / "postings.json"


def fixture_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(FIXTURE.read_text())
    return body


def client(routes: dict[str, httpx2.Response | Exception]) -> BoardClient:
    return BoardClient(
        PINPOINT,
        BoardConfig(boards=(), retry_backoff_seconds=0.0),
        http_client=routing(routes),
        sleeper=never_sleeps,
    )


def run(fetcher: BoardClient, company: str) -> Any:
    return asyncio.run(discover(fetcher, company))


def test_a_board_that_answers_is_reported_unverifiable() -> None:
    fetcher = client({"/postings.json": ok(fixture_body())})

    result = run(fetcher, "Pinpoint")

    assert result.outcome is DiscoveryOutcome.UNVERIFIABLE
    assert result.slug == "pinpoint"


def test_an_unknown_slug_is_reported_as_not_found() -> None:
    fetcher = client({"/postings.json": httpx2.Response(404)})

    result = run(fetcher, "Pinpoint")

    assert result.outcome is DiscoveryOutcome.NOT_FOUND
    assert result.slug is None
