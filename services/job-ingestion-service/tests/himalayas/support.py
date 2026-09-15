"""Shared fixtures and database harness for the Himalayas test suite.

Kept in one place so the four Himalayas test files share one fixture loader,
one feed-envelope builder, and one database harness rather than each carrying
its own near-identical copy.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import PostgresDsn

from job_ingestion.database import Database
from tests.support.catalog import with_empty_catalog

FIXTURES = Path(__file__).parent / "fixtures"


def page_body(name: str = "page_one.json") -> dict[str, Any]:
    body: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return body


def page_records(name: str = "page_one.json") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = page_body(name)["jobs"]
    return records


def posting(**overrides: Any) -> dict[str, Any]:
    """The first fixture posting, with any fields overridden.

    Named `posting` rather than `record`, since every consuming test file
    already uses `record` as the local name for the *validated* model these
    raw dicts feed into.
    """
    base = page_records()[0].copy()
    base.update(overrides)
    return base


def without(*fields: str) -> dict[str, Any]:
    """The first fixture posting, with fields removed."""
    base = posting()
    for field in fields:
        del base[field]
    return base


def feed_page(jobs: list[dict[str, Any]], *, next_cursor: str | None = None) -> dict[str, Any]:
    """One Himalayas feed response envelope around the given postings."""
    return {
        "comments": "cursor pagination",
        "updatedAt": 1755513600,
        "offset": 0,
        "limit": 20,
        "totalCount": len(jobs),
        "nextCursor": next_cursor,
        "jobs": jobs,
    }


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    """Run one integration test against a catalog that starts and ends empty."""

    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())
