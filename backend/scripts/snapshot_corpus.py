"""Take the corpus snapshot the skill-model decision is measured against.

The measurement design is `docs/superpowers/specs/2026-08-23-skill-model-
measurement-design.md`, and this is its first step. The decision it feeds needs
real postings rather than fixtures, and every run so far has been verified in a
database that was then deleted, so there is nothing to decide against.

Two things this deliberately does not do. It does not change what ships: the
wider board list lives here and is passed in as a config, so `DEFAULT_BOARDS`
and every scheduled run stay as they are, and board discovery remains #120's
problem. And it does not keep the database. What survives is the manifest,
because a snapshot that only exists as a running server is not a snapshot.

No provider prose reaches the manifest. Postings are identified by their
provenance keys and summarized by counts, and the corpus is pinned by one
digest over per-posting description hashes rather than by the descriptions.
"""

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import Database
from app.modules.ingestion.arbeitnow.client import ArbeitnowConfig
from app.modules.ingestion.arbeitnow.pipeline import ingest_arbeitnow
from app.modules.ingestion.contracts import IngestionSummary
from app.modules.ingestion.greenhouse.client import DEFAULT_BASE_URL, GreenhouseConfig
from app.modules.ingestion.greenhouse.pipeline import ingest_greenhouse
from app.modules.jobs.models import Job, JobProvenance

# Raised far above the scheduled defaults on purpose. A run that stops at its
# budget is not source-exhausted, and an unexhausted run is not a snapshot of a
# corpus, it is a snapshot of a budget.
SNAPSHOT_MAX_RECORDS = 50_000
SNAPSHOT_MAX_PAGES = 400

# Below this many employers outside engineering, the measurement design says the
# tech bias stands and is reported rather than quietly absorbed.
OUTSIDE_ENGINEERING_FLOOR = 5


@dataclass(frozen=True)
class Board:
    """One Greenhouse board in the snapshot, with the judgement made about it.

    `engineering_employer` is a judgement about the employer, not about any one
    posting, and it is recorded here so the achieved mix can be audited rather
    than asserted.
    """

    token: str
    sector: str
    engineering_employer: bool


# Verified against the boards API before being fixed here, rather than recalled.
# Every token below returned a non-empty job list when the list was assembled.
SNAPSHOT_BOARDS: tuple[Board, ...] = (
    # The three that ship today, kept so the snapshot stays comparable to
    # earlier runs.
    Board("anthropic", "technology", True),
    Board("datadog", "technology", True),
    Board("hudl", "sports technology", True),
    # Further technology employers, mid-sized rather than the largest available,
    # so the engineering half does not simply swamp the corpus by volume.
    Board("discord", "technology", True),
    Board("figma", "technology", True),
    Board("duolingo", "education technology", True),
    Board("carta", "financial technology", True),
    # Employers outside engineering. These are the point of the wider list: a
    # technical dictionary flatters itself on a corpus of technology companies.
    Board("hellofresh", "food retail and logistics", False),
    Board("sweetgreen", "restaurants", False),
    Board("peloton", "consumer fitness", False),
    Board("everlane", "apparel retail", False),
    Board("glossier", "beauty retail", False),
    Board("khanacademy", "education nonprofit", False),
    Board("wikimedia", "nonprofit", False),
    Board("talkspace", "healthcare", False),
)

BOARD_SECTORS = {board.token: board.sector for board in SNAPSHOT_BOARDS}


def snapshot_greenhouse_config() -> GreenhouseConfig:
    """The wider board list, as a config rather than as an edit to the default."""
    return GreenhouseConfig(
        boards=tuple(board.token for board in SNAPSHOT_BOARDS),
        base_url=DEFAULT_BASE_URL,
    )


def describe(summary: IngestionSummary) -> dict[str, Any]:
    """What a run reported, including whether it was entitled to be believed."""
    return {
        "source": summary.source_key,
        "fetched": summary.fetched,
        "created": summary.created,
        "updated": summary.updated,
        "skipped": summary.skipped,
        "failures": len(summary.failures),
        # Reasons, not just a count. A fetch-stage failure aborts pagination,
        # so a truncated corpus and a couple of unusable records look identical
        # in a tally and are not remotely the same thing. These strings are
        # built to describe the problem without repeating provider data.
        "failure_reasons": sorted({f"{f.stage.value}: {f.reason}" for f in summary.failures}),
        "reached_the_end": summary.reached_the_end,
        "stopped_at_budget": summary.stopped_at_budget,
        "processing_complete": summary.processing_complete,
        "source_exhausted": summary.source_exhausted,
    }


async def run_ingests() -> list[dict[str, Any]]:
    """Run both sources to exhaustion, and report what each run was entitled to claim."""
    arbeitnow = await ingest_arbeitnow(
        config=ArbeitnowConfig(max_pages=SNAPSHOT_MAX_PAGES),
        max_records=SNAPSHOT_MAX_RECORDS,
    )
    greenhouse = await ingest_greenhouse(
        config=snapshot_greenhouse_config(),
        max_records=SNAPSHOT_MAX_RECORDS,
    )
    return [describe(arbeitnow), describe(greenhouse)]


def board_of(source_job_id: str) -> str:
    """The board a Greenhouse provenance key came from.

    Greenhouse identifiers are `board:id`, so the board is recoverable without
    reading the untrusted payload back out.
    """
    return source_job_id.split(":", 1)[0]


async def load_jobs(database: Database) -> list[Job]:
    """Every stored job, with the relationships the manifest reads.

    Provenance and its source are both eager-loaded. A lazy load here would
    resume outside the greenlet the async session runs in and fail.
    """
    async with database.session() as session:
        return list(
            (
                await session.execute(
                    select(Job).options(
                        selectinload(Job.company),
                        selectinload(Job.provenance_records).selectinload(JobProvenance.source),
                    )
                )
            )
            .scalars()
            .all()
        )


def summarize(jobs: list[Job]) -> dict[str, Any]:
    """Turn the stored corpus into counts, hashes, and nothing else."""
    by_source: Counter[str] = Counter()
    by_board: Counter[str] = Counter()
    by_employer: Counter[str] = Counter()
    multi_source = 0
    published: list[datetime] = []
    digest_parts: list[str] = []

    for job in jobs:
        sources = set()
        for record in job.provenance_records:
            source_key = record.source.key
            sources.add(source_key)
            by_source[source_key] += 1
            if source_key == "greenhouse":
                by_board[board_of(record.source_job_id)] += 1
            digest_parts.append(f"{source_key}:{record.source_job_id}")
        if len(sources) > 1:
            multi_source += 1
        by_employer[job.company.display_name] += 1
        if job.published_at is not None:
            published.append(job.published_at)
        digest_parts.append(hashlib.sha256(job.description.encode()).hexdigest())

    outside = [board for board in SNAPSHOT_BOARDS if not board.engineering_employer]
    returned = [board.token for board in outside if by_board[board.token]]

    return {
        "taken_at": datetime.now(UTC).isoformat(),
        "corpus_digest": hashlib.sha256("\n".join(sorted(digest_parts)).encode()).hexdigest(),
        "jobs": len(jobs),
        "employer_count": len(by_employer),
        "jobs_with_two_sources": multi_source,
        "published_at_range": {
            "earliest": min(published).isoformat() if published else None,
            "latest": max(published).isoformat() if published else None,
            "postings_without_a_date": len(jobs) - len(published),
        },
        "by_source": dict(sorted(by_source.items())),
        "greenhouse_boards": {
            token: {"postings": count, "sector": BOARD_SECTORS.get(token, "unknown")}
            for token, count in sorted(by_board.items())
        },
        "boards_configured": len(SNAPSHOT_BOARDS),
        "boards_that_returned_postings": len(by_board),
        "employers_outside_engineering": {
            "configured": [board.token for board in outside],
            "returned_postings": returned,
            "floor": OUTSIDE_ENGINEERING_FLOOR,
            "floor_met": len(returned) >= OUTSIDE_ENGINEERING_FLOOR,
        },
        # The largest employers only. The full list is 700-odd names and adds
        # bulk without adding a finding; the count above is what characterizes
        # the corpus.
        "largest_employers": dict(by_employer.most_common(30)),
    }


async def snapshot(destination: Path, *, ingest: bool) -> None:
    runs = await run_ingests() if ingest else []
    database = Database(get_settings().database_url)
    try:
        manifest = summarize(await load_jobs(database))
    finally:
        await database.dispose()
    if runs:
        # This run only. The stored corpus is the union of every run against
        # this database, so the counts above and these numbers answer different
        # questions and a re-run will show few creations and many skips.
        manifest["this_run"] = runs
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Take the skill-model corpus snapshot.")
    parser.add_argument("destination", type=Path, help="where the manifest is written")
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="summarize the database as it stands, without ingesting first",
    )
    arguments = parser.parse_args()
    asyncio.run(snapshot(arguments.destination, ingest=not arguments.manifest_only))


if __name__ == "__main__":
    main()
