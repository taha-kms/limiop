"""The backfill: the same rule, applied to what is already in the database.

Ingestion strips before it writes, so postings stored before that landed keep
their employer's blurb. These tests are about the command changing exactly
those, saying so before it does, and having nothing to do the second time.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from platform_db.models import Company, Job
from pydantic import PostgresDsn
from sqlalchemy import select

from job_ingestion.database import Database
from tests.support.catalog import with_empty_catalog

pytestmark = pytest.mark.integration

SERVICE_ROOT = Path(__file__).resolve().parents[1]
BLURB = "Acme is a public benefit corporation headquartered in San Francisco."
REQUIREMENT = "Working fluency with data, including SQL."


def strip_stored(database_url: PostgresDsn, *, apply: bool = False) -> dict[str, Any]:
    """Run the command the way an operator would, and read what it reported."""
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.strip_stored_boilerplate",
            "--database-url",
            str(database_url),
            *(["--apply"] if apply else []),
        ],
        cwd=SERVICE_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report: dict[str, Any] = json.loads(completed.stdout)
    return report


async def seed(database: Database, *, count: int = 5, employer: str = "Acme GmbH") -> None:
    async with database.session() as session:
        company = Company(display_name=employer)
        session.add(company)
        await session.flush()
        for index in range(count):
            session.add(
                Job(
                    company_id=company.id,
                    match_key=f"v1:stored-{employer}-{index}",
                    title=f"Engineer {index}",
                    description=f"{BLURB}\n{REQUIREMENT}\nRole {index}.",
                    application_url=f"https://acme.example.com/jobs/{index}",
                )
            )
        await session.commit()


async def descriptions(database: Database) -> list[str]:
    async with database.session() as session:
        return list(await session.scalars(select(Job.description).order_by(Job.title)))


def exercise(database_url: PostgresDsn, test: object) -> None:
    async def go() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)  # type: ignore[arg-type]
        finally:
            await database.dispose()

    asyncio.run(go())


def test_a_dry_run_reports_what_it_would_change_and_changes_nothing(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        await seed(database)

        report = strip_stored(database_url)

        assert report["postings_changed"] == 5
        assert report["blocks_removed"] == 5
        assert report["written"] is False
        assert all(BLURB in description for description in await descriptions(database))

    exercise(database_url, test)


def test_applying_removes_the_blurb_and_keeps_the_requirement(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        await seed(database)

        report = strip_stored(database_url, apply=True)

        assert report["postings_changed"] == 5
        stored = await descriptions(database)
        assert all(BLURB not in description for description in stored)
        assert all(REQUIREMENT in description for description in stored)
        assert all(f"Role {index}." in stored[index] for index in range(5))

    exercise(database_url, test)


def test_running_it_twice_changes_nothing_the_second_time(database_url: PostgresDsn) -> None:
    """A stripped description no longer carries the block, and a block no
    posting carries is not a block."""

    async def test(database: Database) -> None:
        await seed(database)
        strip_stored(database_url, apply=True)
        before = await descriptions(database)

        report = strip_stored(database_url, apply=True)

        assert report["postings_changed"] == 0
        assert await descriptions(database) == before

    exercise(database_url, test)


def test_an_employer_with_too_few_postings_is_left_alone(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        await seed(database, count=4)

        report = strip_stored(database_url, apply=True)

        assert report["postings_changed"] == 0
        assert all(BLURB in description for description in await descriptions(database))

    exercise(database_url, test)
