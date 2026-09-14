"""Run one website-resolution pass and report what it did.

Thin over `job_ingestion.boards.websites`: the strategies, the budget, and
the recheck window all live there so they stay testable without a
subprocess. This script only wires a database URL to them and prints what
changed, so an operator or a scheduled job can see it without a debugger.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime

from platform_db.models import Company
from pydantic import PostgresDsn
from sqlalchemy import select

from job_ingestion.boards.websites import resolve_websites
from job_ingestion.config import Settings
from job_ingestion.database import Database

# Resolution makes at most one network request per company (Wikidata), and a
# script run by hand should not become an unannounced crawl of its API.
DEFAULT_LIMIT = 25


async def report(database_url: str, limit: int) -> dict[str, object]:
    started_at = datetime.now(UTC)
    settings = Settings(database_url=PostgresDsn(database_url))
    summary = await resolve_websites(settings=settings, budget=limit)

    database = Database(database_url)
    try:
        async with database.session() as session:
            statement = (
                select(Company.display_name, Company.website_url, Company.website_source)
                .where(
                    Company.website_url.is_not(None),
                    Company.website_checked_at >= started_at,
                )
                .order_by(Company.display_name)
            )
            resolved = [
                {"company": display_name, "website_url": website_url, "source": source}
                for display_name, website_url, source in (await session.execute(statement)).all()
            ]
    finally:
        await database.dispose()

    return {"summary": asdict(summary), "resolved": resolved}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    arguments = parser.parse_args()

    json.dump(asyncio.run(report(arguments.database_url, arguments.limit)), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
