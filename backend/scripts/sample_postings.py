"""Identify each posting's language, then draw the annotation sample.

Steps 2 and 3 of the measurement design. They live together because the second
depends on the first: the sampling frame is the English postings, so the frame
does not exist until every posting has been classified.

Two things are deliberate. The detector is `py3langid`, which is deterministic;
`langdetect` seeds from a random source and answers differently across runs,
which would make the frame irreproducible. And the sample is drawn under a
fixed, recorded seed and committed before annotation begins, so it cannot be
adjusted once someone has seen what is in it.

The committed sample holds provenance keys and description hashes. It holds no
provider prose: annotators read the postings from the snapshot database.
"""

import argparse
import asyncio
import hashlib
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import py3langid
from platform_db.models import Job, JobProvenance
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import Database

# Recorded rather than chosen at run time, so the draw can be reproduced.
SAMPLE_SEED = 20260823
SAMPLE_SIZE = 80

# Enough text to classify on. Titles alone are too short to be reliable, and
# whole descriptions are slower without being more accurate.
CLASSIFY_CHARS = 1200


@dataclass(frozen=True)
class Posting:
    """One stored posting, reduced to what sampling and annotation need."""

    key: str
    stratum: str
    language: str
    description_sha256: str


def detect(text: str) -> str:
    """The language of a posting, as `en`, `de`, or `other`."""
    code, _ = py3langid.classify(text[:CLASSIFY_CHARS])
    return code if code in {"en", "de"} else "other"


def stratum_of(source_key: str, source_job_id: str) -> str:
    """The stratum a posting is sampled within.

    Greenhouse is stratified by board, because the boards are different
    employers with different role mixes and one of them could otherwise take
    the whole allocation.
    """
    if source_key == "greenhouse":
        return f"greenhouse:{source_job_id.split(':', 1)[0]}"
    return source_key


async def load_postings(database: Database) -> list[Posting]:
    async with database.session() as session:
        jobs = (
            (
                await session.execute(
                    select(Job).options(
                        selectinload(Job.provenance_records).selectinload(JobProvenance.source)
                    )
                )
            )
            .scalars()
            .all()
        )

    postings = []
    for job in jobs:
        # A job may carry provenance from several sources. It is sampled under
        # the source that is lowest alphabetically, so the choice is stable
        # across runs rather than dependent on row order.
        records = sorted(job.provenance_records, key=lambda r: (r.source.key, r.source_job_id))
        first = records[0]
        postings.append(
            Posting(
                key=f"{first.source.key}:{first.source_job_id}",
                stratum=stratum_of(first.source.key, first.source_job_id),
                language=detect(f"{job.title}\n{job.description}"),
                description_sha256=hashlib.sha256(job.description.encode()).hexdigest(),
            )
        )
    return postings


def allocate(strata: dict[str, list[Posting]], size: int) -> dict[str, int]:
    """Split the sample across strata in proportion to their size.

    Largest-remainder, so the parts sum to the whole. Every non-empty stratum
    gets at least one posting: a board contributing nothing to the sample is a
    board the measurement cannot say anything about, and the wider board list
    exists precisely so the smaller employers are represented.
    """
    total = sum(len(members) for members in strata.values())
    exact = {name: len(members) * size / total for name, members in strata.items()}
    floors = {name: max(1, int(share)) for name, share in exact.items()}

    while sum(floors.values()) > size:
        largest = max(floors, key=lambda name: (floors[name], -exact[name]))
        if floors[largest] == 1:
            break
        floors[largest] -= 1
    remainders = sorted(strata, key=lambda name: exact[name] - int(exact[name]), reverse=True)
    index = 0
    while sum(floors.values()) < size:
        name = remainders[index % len(remainders)]
        if floors[name] < len(strata[name]):
            floors[name] += 1
        index += 1
    return floors


def draw(postings: list[Posting], size: int) -> tuple[list[Posting], dict[str, int]]:
    english = [posting for posting in postings if posting.language == "en"]
    strata: dict[str, list[Posting]] = defaultdict(list)
    for posting in english:
        strata[posting.stratum].append(posting)
    for members in strata.values():
        members.sort(key=lambda posting: posting.key)

    quota = allocate(dict(strata), size)
    generator = random.Random(SAMPLE_SEED)
    sample = []
    for name in sorted(strata):
        sample.extend(generator.sample(strata[name], min(quota[name], len(strata[name]))))
    sample.sort(key=lambda posting: posting.key)
    return sample, quota


def report(postings: list[Posting], sample: list[Posting], quota: dict[str, int]) -> dict[str, Any]:
    languages: Counter[str] = Counter(posting.language for posting in postings)
    by_source_language: dict[str, Counter[str]] = defaultdict(Counter)
    for posting in postings:
        by_source_language[posting.key.split(":", 1)[0]][posting.language] += 1

    english = languages["en"]
    return {
        "detector": "py3langid 0.3.0",
        "seed": SAMPLE_SEED,
        "postings": len(postings),
        "languages": dict(languages.most_common()),
        "share_english": round(english / len(postings), 4) if postings else 0.0,
        "share_not_servable_by_an_english_only_v1": (
            round(1 - english / len(postings), 4) if postings else 0.0
        ),
        "by_source": {
            source: dict(counts.most_common())
            for source, counts in sorted(by_source_language.items())
        },
        "sampling_frame": english,
        "sample_size": len(sample),
        "quota_by_stratum": dict(sorted(quota.items())),
        "sample": [
            {"posting": posting.key, "description_sha256": posting.description_sha256}
            for posting in sample
        ],
    }


async def run(destination: Path) -> None:
    database = Database(get_settings().database_url)
    try:
        postings = await load_postings(database)
    finally:
        await database.dispose()
    sample, quota = draw(postings, SAMPLE_SIZE)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report(postings, sample, quota), indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify languages and draw the sample.")
    parser.add_argument("destination", type=Path, help="where the sample is written")
    asyncio.run(run(parser.parse_args().destination))


if __name__ == "__main__":
    main()
