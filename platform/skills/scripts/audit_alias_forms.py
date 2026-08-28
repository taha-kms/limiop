"""Report how each alias-table surface form behaves across a live job catalog.

Firing counts alone mislead when one employer contributes half the postings and
repeats the same boilerplate in every one: a form can appear in 500 postings and
one employer. Counts are therefore reported per employer as well as per posting,
and sampled contexts are drawn at most once per employer so shared boilerplate
cannot fill the sample.

The catalog text is not committed, so this script reads it from a database
holding the catalog and writes its output wherever the caller asks.
"""

import argparse
import json
import os
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlparse
from uuid import UUID

from platform_skills import extract_mentions

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VOCABULARY = REPOSITORY_ROOT / "backend/app/modules/skills/data/aliases.v2.json"
CONTEXT_WINDOW = 60
SAMPLES_PER_FORM = 8

CATALOG_QUERY = """
select json_build_object(
  'employer', c.display_name,
  'description', j.description
)::text
from jobs j
join companies c on c.id = j.company_id
where j.description is not null and j.description <> ''
order by c.display_name, j.id
"""


def load_vocabulary(path: Path) -> dict[str, UUID | None]:
    document = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    rows = cast(list[dict[str, object]], document["surface_forms"])
    vocabulary: dict[str, UUID | None] = {}
    for row in rows:
        concepts = cast(list[str], row["concept_ids"])
        surface_form = cast(str, row["surface_form"])
        vocabulary[surface_form] = UUID(concepts[0]) if len(concepts) == 1 else None
    return vocabulary


def psql_connection(database_url: str) -> tuple[list[str], dict[str, str]]:
    """Read the catalog through psql, as the sibling recovery script does.

    ``platform/skills`` deliberately carries no database driver: the package it
    ships is pure, and a script is not a reason to add psycopg to it.
    """
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("database URL must use postgresql or postgresql+psycopg")
    if parsed.hostname is None or parsed.username is None or not parsed.path.strip("/"):
        raise ValueError("database URL must include host, user, and database")

    command = [
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
        CATALOG_QUERY,
    ]
    environment = dict(os.environ)
    if parsed.password is not None:
        environment["PGPASSWORD"] = unquote(parsed.password)
    return command, environment


def read_postings(database_url: str) -> list[tuple[str, str]]:
    command, environment = psql_connection(database_url)
    result = subprocess.run(command, check=True, capture_output=True, text=True, env=environment)

    postings: list[tuple[str, str]] = []
    for line_number, line in enumerate(result.stdout.splitlines(), start=1):
        if not line:
            continue
        row = cast(dict[str, object], json.loads(line))
        employer = row.get("employer")
        description = row.get("description")
        if not isinstance(employer, str) or not isinstance(description, str):
            raise ValueError(f"psql output line {line_number} is not an employer and a description")
        postings.append((employer, description))
    return postings


def audit(
    postings: list[tuple[str, str]],
    vocabulary: dict[str, UUID | None],
    *,
    seed: int,
) -> tuple[dict[str, object], dict[str, list[str]]]:
    companies = {company for company, _ in postings}
    mentions: Counter[str] = Counter()
    posting_hits: Counter[str] = Counter()
    employers: defaultdict[str, set[str]] = defaultdict(set)
    contexts: defaultdict[str, dict[str, str]] = defaultdict(dict)

    for company, text in postings:
        seen: set[str] = set()
        for mention in extract_mentions(text, vocabulary):
            form = mention.normalized_form
            mentions[form] += 1
            seen.add(form)
            if company not in contexts[form]:
                start, end = mention.span
                left = text[max(0, start - CONTEXT_WINDOW) : start]
                right = text[end : end + CONTEXT_WINDOW]
                contexts[form][company] = f"…{left}»{text[start:end]}«{right}…".replace("\n", " ")
        for form in seen:
            posting_hits[form] += 1
            employers[form].add(company)

    report: dict[str, object] = {
        "postings": len(postings),
        "employers": len(companies),
        "total_mentions": sum(mentions.values()),
        "mentions_per_posting": round(sum(mentions.values()) / len(postings), 1),
        "forms_in_vocabulary": len(vocabulary),
        "forms_that_fired": len(mentions),
        "per_form": [
            {
                "surface_form": form,
                "mentions": mentions[form],
                "postings": posting_hits[form],
                "employers": len(employers[form]),
                "employer_rate": round(len(employers[form]) / len(companies), 4),
            }
            for form in sorted(mentions, key=lambda form: (-len(employers[form]), form))
        ],
    }

    generator = random.Random(seed)
    samples = {
        form: generator.sample(sorted(by_company.values()), min(SAMPLES_PER_FORM, len(by_company)))
        for form, by_company in contexts.items()
    }
    return report, samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True, help="a catalog database")
    parser.add_argument("--vocabulary", type=Path, default=DEFAULT_VOCABULARY)
    parser.add_argument("--counts", type=Path, required=True)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=193)
    arguments = parser.parse_args()

    postings = read_postings(arguments.database_url)
    if not postings:
        parser.error("the catalog holds no postings with descriptions")

    report, samples = audit(postings, load_vocabulary(arguments.vocabulary), seed=arguments.seed)
    arguments.counts.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    arguments.contexts.write_text(json.dumps(samples, indent=2) + "\n", encoding="utf-8")

    summary = {key: value for key, value in report.items() if key != "per_form"}
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
