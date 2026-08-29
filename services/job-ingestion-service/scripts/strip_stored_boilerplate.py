"""Apply the employer-boilerplate rule to descriptions already stored.

Ingestion strips before it writes, so a posting stored before that landed keeps
its employer's blurb until the source is read again. This applies the same rule
to what is in the database now.

Reports first and writes only when told to. It is the same rule, so running it
twice changes nothing the second time: a stripped description no longer carries
the block, and a block no posting carries is not a block.

Skills are not re-extracted. Ingestion does that on its next pass over each
posting, inside the transaction that stores it, and repeating those rules here
would put them in two places.
"""

import argparse
import asyncio
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from platform_db.models import Company, Job
from sqlalchemy import select, update

from job_ingestion.boilerplate import BoilerplatePolicy, blocks_to_remove, without_blocks
from job_ingestion.database import Database


@dataclass(frozen=True, slots=True)
class Rewrite:
    """One posting whose stored description would change."""

    job_id: UUID
    description: str
    removed_blocks: int
    removed_characters: int


async def read_postings(database: Database) -> list[tuple[UUID, str, str]]:
    """Every stored posting as (id, employer, description)."""
    async with database.session() as session:
        rows = await session.execute(
            select(Job.id, Company.normalized_name, Job.description).join(
                Company, Company.id == Job.company_id
            )
        )
        return [(job_id, str(employer), str(description)) for job_id, employer, description in rows]


def rewrites(postings: Sequence[tuple[UUID, str, str]], policy: BoilerplatePolicy) -> list[Rewrite]:
    by_employer: dict[str, list[str]] = defaultdict(list)
    for _, employer, description in postings:
        by_employer[employer].append(description)

    removable = blocks_to_remove(by_employer, policy)
    changed = []
    for job_id, employer, description in postings:
        stripped = without_blocks(description, removable[employer])
        if stripped == description:
            continue
        changed.append(
            Rewrite(
                job_id=job_id,
                description=stripped,
                removed_blocks=len(description.splitlines()) - len(stripped.splitlines()),
                removed_characters=len(description) - len(stripped),
            )
        )
    return changed


async def apply(database: Database, changes: Sequence[Rewrite]) -> None:
    """Write the rewritten descriptions, one transaction for the batch."""
    async with database.session() as session:
        for change in changes:
            await session.execute(
                update(Job).where(Job.id == change.job_id).values(description=change.description)
            )
        await session.commit()


async def run(database_url: str, policy: BoilerplatePolicy, *, write: bool) -> dict[str, object]:
    database = Database(database_url)
    try:
        postings = await read_postings(database)
        changes = rewrites(postings, policy)
        if write:
            await apply(database, changes)
        return {
            "postings_read": len(postings),
            "postings_changed": len(changes),
            "blocks_removed": sum(change.removed_blocks for change in changes),
            "characters_removed": sum(change.removed_characters for change in changes),
            "written": write,
        }
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the rewritten descriptions; without it nothing is changed",
    )
    parser.add_argument(
        "--minimum-postings", type=int, default=BoilerplatePolicy().minimum_postings
    )
    parser.add_argument("--minimum-share", type=float, default=BoilerplatePolicy().minimum_share)
    arguments = parser.parse_args()

    policy = BoilerplatePolicy(
        minimum_postings=arguments.minimum_postings,
        minimum_share=arguments.minimum_share,
    )
    print(
        json.dumps(
            asyncio.run(run(arguments.database_url, policy, write=arguments.apply)), indent=2
        )
    )


if __name__ == "__main__":
    main()
