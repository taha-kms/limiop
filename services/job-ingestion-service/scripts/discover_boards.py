"""Report which stored companies have a findable board on one provider.

A discovery report, not a configuration change. It says what was found, what
resolved to somebody else, and what could not be found at all — and adding a
board to the polled list stays a deliberate act, because the cost of polling one
that belongs to another company is filing their postings under the wrong
employer.

The catalogue is not committed, so companies are read from a database holding it.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from urllib.parse import unquote, urlparse

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.discovery import DiscoveryOutcome, discover
from job_ingestion.boards.pipeline import configured_base_url
from job_ingestion.boards.registry import provider_for
from job_ingestion.config import get_settings

# Boards are polled by a scheduler and guessed one at a time. A limit keeps a
# report from becoming an unannounced crawl of somebody's API.
DEFAULT_LIMIT = 25

COMPANIES = """
select c.display_name
from companies c
join jobs j on j.company_id = c.id
group by c.id, c.display_name
order by count(*) desc, c.display_name
limit {limit}
"""


def companies(database_url: str, limit: int) -> list[str]:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("database URL must use postgresql or postgresql+psycopg")
    if parsed.hostname is None or parsed.username is None or not parsed.path.strip("/"):
        raise ValueError("database URL must include host, user, and database")

    environment = dict(os.environ)
    if parsed.password is not None:
        environment["PGPASSWORD"] = unquote(parsed.password)
    result = subprocess.run(
        [
            "psql",
            "-X",
            "--host",
            parsed.hostname,
            "--port",
            str(parsed.port or 5432),
            "--username",
            unquote(parsed.username),
            "--dbname",
            unquote(parsed.path.strip("/")),
            "--no-align",
            "--tuples-only",
            "--set",
            "ON_ERROR_STOP=1",
            "--command",
            COMPANIES.format(limit=limit),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


async def report(names: list[str], source_key: str) -> dict[str, object]:
    provider = provider_for(source_key)
    config = BoardConfig(boards=(), base_url=configured_base_url(provider, get_settings()))
    async with BoardClient(provider, config) as client:
        results = [await discover(client, name) for name in names]

    counts = Counter(result.outcome.value for result in results)
    return {
        "source": source_key,
        "checked": len(results),
        "outcomes": dict(sorted(counts.items())),
        # Everything is listed, including what was not found. A report that
        # only showed successes would make the gap invisible, which is the
        # thing a hand-written list already does.
        "results": [asdict(result) for result in results],
        "confirmed": sorted(
            result.slug
            for result in results
            if result.outcome is DiscoveryOutcome.CONFIRMED and result.slug
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--source", default="greenhouse", help="registered board provider key")
    arguments = parser.parse_args()

    names = companies(arguments.database_url, arguments.limit)
    json.dump(asyncio.run(report(names, arguments.source)), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
