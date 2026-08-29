"""Measure what removing employer boilerplate does to the candidate inbox.

Reads the stored catalogue, applies the rule in `job_ingestion.boilerplate` to
the descriptions as they are, and counts what the candidate generator would
propose before and after. Nothing is written: this measures the rule, it does
not apply it to stored rows.

Counts are proposals rather than the stored inbox. The inbox holds only what
the vocabulary could not resolve, so it is a subset of this; measuring the
generator's output keeps both sides of the comparison the same quantity.

Ranked by employers as well as mentions, because one employer contributes half
this catalogue and a mention count there measures who is hiring.
"""

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from collections.abc import Sequence

from platform_db.models import Company, Job
from platform_skills.candidates import propose
from sqlalchemy import select

from job_ingestion.boilerplate import BoilerplatePolicy, blocks_to_remove, without_blocks
from job_ingestion.database import Database

# The terms #245 named, from twenty observations read by hand.
WATCHED = (
    "San",
    "Safety",
    "Concrete",
    "Neurons",
    "anthropic.com/careers",
    "About Anthropic Anthropic",
)

Posting = tuple[str, str]


async def read_postings(database_url: str) -> list[Posting]:
    """Every stored posting as (employer, description)."""
    database = Database(database_url)
    try:
        async with database.session() as session:
            rows = await session.execute(
                select(Company.display_name, Job.description).join(
                    Job, Job.company_id == Company.id
                )
            )
            return [(str(name), str(description)) for name, description in rows]
    finally:
        await database.dispose()


def stripped(postings: Sequence[Posting], policy: BoilerplatePolicy) -> list[Posting]:
    by_employer: dict[str, list[str]] = defaultdict(list)
    for employer, description in postings:
        by_employer[employer].append(description)

    removable = blocks_to_remove(by_employer, policy)
    return [
        (employer, without_blocks(description, removable[employer]))
        for employer, description in postings
    ]


def measure(postings: Sequence[Posting]) -> dict[str, object]:
    mentions: Counter[str] = Counter()
    employers: dict[str, set[str]] = defaultdict(set)

    for employer, description in postings:
        for candidate in propose(description):
            # Whitespace-collapsed, as the inbox stores it. A term that spans a
            # line break is one term, not a spelling of its own.
            term = " ".join(candidate.surface_form.split())
            mentions[term] += 1
            employers[term].add(employer)

    return {
        "observations": sum(mentions.values()),
        "distinct_terms": len(mentions),
        "characters": sum(len(description) for _, description in postings),
        "watched": {
            term: {"mentions": mentions.get(term, 0), "employers": len(employers.get(term, ()))}
            for term in WATCHED
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--minimum-postings", type=int, default=BoilerplatePolicy().minimum_postings
    )
    parser.add_argument("--minimum-share", type=float, default=BoilerplatePolicy().minimum_share)
    arguments = parser.parse_args()

    policy = BoilerplatePolicy(
        minimum_postings=arguments.minimum_postings,
        minimum_share=arguments.minimum_share,
    )
    postings = asyncio.run(read_postings(arguments.database_url))
    after = stripped(postings, policy)

    print(
        json.dumps(
            {
                "postings": len(postings),
                "employers": len({employer for employer, _ in postings}),
                "policy": {
                    "minimum_postings": policy.minimum_postings,
                    "minimum_share": policy.minimum_share,
                },
                "before": measure(postings),
                "after": measure(after),
                "postings_changed": sum(
                    1
                    for (_, before), (_, cleaned) in zip(postings, after, strict=True)
                    if before != cleaned
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
