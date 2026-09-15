"""Shared fixtures and database harness for the Adzuna test suite.

The fixture pages are hand-written to the documented response shape, since no
credentials exist to record a live one. A raw fixture result carries no
`country`: the client stamps that on every record it yields, so the helpers
here stamp it the same way before a record reaches validation.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import httpx2
from platform_db.models import IngestionRun, SourceQuotaUsage
from pydantic import PostgresDsn
from sqlalchemy import delete

from job_ingestion.adzuna.source import SOURCE_KEY
from job_ingestion.database import Database
from tests.support.catalog import with_empty_catalog

FIXTURES = Path(__file__).parent / "fixtures"


def page_body(country: str = "gb") -> dict[str, Any]:
    """One documented search response for `country`, as the API would send it."""
    body: dict[str, Any] = json.loads((FIXTURES / f"{country}_page_1.json").read_text())
    return body


def stamped(record: dict[str, Any], country: str) -> dict[str, Any]:
    """A fixture result as the client yields it: with its country on it."""
    return {**record, "country": country}


def page_records(country: str = "gb") -> list[dict[str, Any]]:
    """Every result of one fixture page, stamped the way the client stamps them."""
    return [stamped(record, country) for record in page_body(country)["results"]]


def posting(**overrides: Any) -> dict[str, Any]:
    """The first British fixture result, stamped, with any fields overridden."""
    return {**page_records()[0], **overrides}


def without(*fields: str) -> dict[str, Any]:
    """The first British fixture result with top-level fields removed."""
    record = posting()
    for field in fields:
        del record[field]
    return record


def search_page(results: list[dict[str, Any]]) -> dict[str, Any]:
    """One search response envelope around the given results."""
    return {"count": len(results), "mean": 50000.0, "results": results}


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    """Run one integration test against a catalog and quota ledger that start empty.

    Adzuna is the first source whose tests touch the quota ledger and the
    run log as well as the catalog, so both are cleared for this source
    alongside it; `with_empty_catalog` knows nothing about either.
    """

    async def clear_source_bookkeeping(database: Database) -> None:
        async with database.session() as session:
            await session.execute(
                delete(SourceQuotaUsage).where(SourceQuotaUsage.source_key == SOURCE_KEY)
            )
            await session.execute(delete(IngestionRun).where(IngestionRun.source_key == SOURCE_KEY))
            await session.commit()

    async def run() -> None:
        database = Database(database_url)
        try:
            await clear_source_bookkeeping(database)
            await with_empty_catalog(database, test)
        finally:
            await clear_source_bookkeeping(database)
            await database.dispose()

    asyncio.run(run())


def recording(
    *replies: httpx2.Response | Exception,
) -> tuple[httpx2.AsyncClient, list[httpx2.Request]]:
    """A client answering each request with the next reply, keeping every request.

    The requests are kept because the test that matters most here asks what
    the client sent, not only what it got back: the credentials must be in
    the query and nowhere else.
    """
    remaining: Iterator[httpx2.Response | Exception] = iter(replies)
    requests: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        reply = next(remaining)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle)), requests
