"""Run one discovery pass against the registry and report what it wrote.

This registers; nothing is polled that was not verified. A guess that answers
for somebody else, or answers nothing at all, is stored as what it was rather
than tried again next run, and the report below shows every row this pass
touched — including the negatives — so the gap discovery could not close
stays visible instead of vanishing.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime

from pydantic import PostgresDsn

from job_ingestion.boards.discovery_run import DiscoveryConfig, discover_boards
from job_ingestion.boards.operator import list_boards
from job_ingestion.boards.registry import provider_for
from job_ingestion.config import Settings
from job_ingestion.database import Database

# A discovery run is guessing, not polling on a schedule; a limit keeps one
# invocation from becoming an unannounced crawl of somebody's API.
DEFAULT_LIMIT = 25
DEFAULT_POLITENESS = 0.5


async def run(
    database_url: str, source_key: str, limit: int, politeness: float
) -> dict[str, object]:
    provider = provider_for(source_key)
    settings = Settings(database_url=PostgresDsn(database_url))
    config = DiscoveryConfig(budget=limit, politeness_seconds=politeness)
    started = datetime.now(UTC)

    summary = await discover_boards(provider, config=config, settings=settings)

    database = Database(settings.database_url)
    try:
        async with database.session() as session:
            rows = await list_boards(session, provider)
    finally:
        await database.dispose()

    written = [
        row
        for row in rows
        if row["last_checked_at"] is not None
        and datetime.fromisoformat(str(row["last_checked_at"])) >= started
    ]

    return {"summary": asdict(summary), "written": written}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source", default="greenhouse", help="registered board provider key")
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help="probe budget for this run"
    )
    parser.add_argument(
        "--politeness", type=float, default=DEFAULT_POLITENESS, help="seconds between companies"
    )
    arguments = parser.parse_args()

    result = asyncio.run(
        run(arguments.database_url, arguments.source, arguments.limit, arguments.politeness)
    )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
