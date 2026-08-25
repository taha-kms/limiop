"""Insert a fixed, recognisable catalogue.

Used by the browser test, which needs data it can assert on, and by anyone who
wants a populated catalogue without calling a third party. Running the real
ingestion would work for the second case and not the first: the live board
changes hourly, so a test written against it asserts on whatever was posted
that morning.

Idempotent. Every row is keyed on a provenance identifier, so running it twice
refreshes rather than duplicates.
"""

import asyncio
from datetime import UTC, datetime

from job_ingestion.config import get_settings
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration, persist_job
from job_ingestion.schemas import NormalizedJob

SOURCE = SourceRegistration(
    key="seed",
    display_name="Seeded catalogue",
    base_url="https://seed.example.com",
)

SEEDED_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)


def posting(
    number: int,
    *,
    title: str,
    company: str,
    description: str,
    location: str | None,
    workplace_type: str,
    employment_type: str,
) -> NormalizedJob:
    """One posting, dated so the newest-first order is fixed rather than incidental."""
    return NormalizedJob.model_validate(
        {
            "company": {"display_name": company},
            "title": title,
            "description": description,
            "location": location,
            "workplace_type": workplace_type,
            "employment_type": employment_type,
            "application_url": f"https://employer.example.com/apply/{number}",
            "published_at": datetime(2026, 1, number, 12, tzinfo=UTC),
            "provenance": {
                "source_key": SOURCE.key,
                "source_job_id": f"seed-{number:03d}",
                "source_url": f"https://seed.example.com/postings/{number}",
            },
        }
    )


POSTINGS = (
    posting(
        1,
        title="Warehouse Coordinator",
        company="Northwind Logistics",
        description="Coordinate inbound shipments.\nKeep the floor plan current.",
        location="Hamburg",
        workplace_type="onsite",
        employment_type="full-time",
    ),
    posting(
        2,
        title="Junior Frontend Developer",
        company="Meridian Software",
        description="Build interfaces with a small team.\nPair regularly.",
        location="Berlin",
        workplace_type="hybrid",
        employment_type="part-time",
    ),
    posting(
        3,
        title="Remote Data Engineer",
        company="Meridian Software",
        description="Build the pipelines the analytics team depends on.\nOwn them end to end.",
        location="Berlin",
        workplace_type="remote",
        employment_type="full-time",
    ),
    posting(
        4,
        title="Data Science Intern",
        company="Halcyon Analytics",
        description="Support the modelling team for six months.",
        location="Munich",
        workplace_type="remote",
        employment_type="internship",
    ),
)


class SeedFailed(RuntimeError):
    """A posting could not be written."""


async def seed() -> int:
    """Write every posting, or say which one could not be written.

    Persistence reports a failed record as a value rather than raising, because
    an ingestion run has to survive one bad record. A seeder has the opposite
    obligation: it exists so something downstream can rely on the rows being
    there, and reporting success over a failed write would send the browser test
    looking for jobs that were never stored.
    """
    database = Database(get_settings().database_url)
    written = 0
    try:
        async with database.session() as session:
            for incoming in POSTINGS:
                result = await persist_job(session, incoming, source=SOURCE, seen_at=SEEDED_AT)
                await session.commit()
                if result.failure is not None:
                    raise SeedFailed(
                        f"{incoming.provenance.source_job_id}: {result.failure.reason}"
                    )
                written += 1
    finally:
        await database.dispose()

    if written != len(POSTINGS):
        raise SeedFailed(f"wrote {written} of {len(POSTINGS)} postings")
    return written


if __name__ == "__main__":
    print(f"seeded {asyncio.run(seed())} postings")
