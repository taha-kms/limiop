"""Finding Polymer's demo organisation without anyone typing its slug."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx2

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.discovery import DiscoveryOutcome, discover
from job_ingestion.polymer.provider import POLYMER
from tests.boards.fakes import never_sleeps, ok, routing

LIST_FIXTURE = Path(__file__).parent / "fixtures" / "list.json"
DETAIL_FIXTURE = Path(__file__).parent / "fixtures" / "detail.json"


def list_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(LIST_FIXTURE.read_text())
    return body


def detail_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(DETAIL_FIXTURE.read_text())
    return body


def client(routes: dict[str, httpx2.Response | Exception]) -> BoardClient:
    return BoardClient(
        POLYMER,
        BoardConfig(boards=(), retry_backoff_seconds=0.0),
        http_client=routing(routes),
        sleeper=never_sleeps,
    )


def run(fetcher: BoardClient, company: str) -> Any:
    return asyncio.run(discover(fetcher, company))


def test_a_board_stating_the_right_company_is_confirmed() -> None:
    fetcher = client(
        {
            "/v1/hire/organizations/aperturelabs/jobs": ok(list_body()),
            "/v1/hire/organizations/aperturelabs/jobs/30084": ok(detail_body()),
        }
    )

    result = run(fetcher, "Aperture Labs")

    assert result.outcome is DiscoveryOutcome.CONFIRMED
    assert result.slug == "aperturelabs"
    assert result.found_company == "Aperture Labs"


def test_an_unknown_slug_is_reported_as_not_found() -> None:
    """An unknown organisation answers 422, the same as any other guess that fails."""
    missing = httpx2.Response(422, json={"errors": {"organization": ["could not be found"]}})
    fetcher = client(
        {
            "/v1/hire/organizations/aperturelabs/jobs": missing,
            "/v1/hire/organizations/aperture-labs/jobs": missing,
            "/v1/hire/organizations/aperture/jobs": missing,
        }
    )

    result = run(fetcher, "Aperture Labs")

    assert result.outcome is DiscoveryOutcome.NOT_FOUND
    assert result.slug is None
