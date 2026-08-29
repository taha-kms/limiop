"""The review queue for promoting an observed term into the vocabulary.

`job_skill_mentions` holds what the candidate generator proposed and the
admission gate refused. Most of it is noise, some of it is boilerplate from one
employer, and a minority are real skills the vocabulary has never heard of.

Ranked by the number of distinct employers rather than by mentions. One
employer contributes half the catalogue and repeats itself in every posting, so
a mention count measures who is hiring — the same correction the alias audit had
to make, recorded in docs/skill-model-measurement/alias-collision-audit.md.

The catalogue text is not committed, so this reads it from a database holding
it. Output is a queue for a person, not a promotion: nothing here changes the
vocabulary, and the decision that it cannot is #152.
"""

import argparse
import json
import os
import subprocess
import sys
from typing import cast
from urllib.parse import unquote, urlparse

DEFAULT_LIMIT = 100
CONTEXT_WINDOW = 60

# Aggregated first, then one example joined back. Grouping the context in with
# the counts would put every posting in its own group and make each term look
# like it belonged to one employer.
QUERY = """
with ranked as (
  select
    m.surface_form,
    count(distinct c.id) as employers,
    sum(m.occurrences) as mentions,
    count(distinct m.job_id) as postings,
    min(m.id::text) as example_id
  from job_skill_mentions m
  join jobs j on j.id = m.job_id
  join companies c on c.id = j.company_id
  group by m.surface_form
  order by count(distinct c.id) desc, sum(m.occurrences) desc, m.surface_form
  limit {limit}
)
select json_build_object(
  'surface_form', r.surface_form,
  'employers', r.employers,
  'mentions', r.mentions,
  'postings', r.postings,
  'example', substring(
    regexp_replace(j.description, '\\s+', ' ', 'g')
    from greatest(1, ((m.evidence->'spans'->0->>0)::int) - {window})
    for {width}
  )
)::text
from ranked r
join job_skill_mentions m on m.id::text = r.example_id
join jobs j on j.id = m.job_id
order by r.employers desc, r.mentions desc, r.surface_form
"""


def psql_command(database_url: str, statement: str) -> tuple[list[str], dict[str, str]]:
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
        statement,
    ]
    environment = dict(os.environ)
    if parsed.password is not None:
        environment["PGPASSWORD"] = unquote(parsed.password)
    return command, environment


def rank(database_url: str, limit: int) -> list[dict[str, object]]:
    statement = QUERY.format(limit=limit, window=CONTEXT_WINDOW, width=CONTEXT_WINDOW * 2)
    command, environment = psql_command(database_url, statement)
    result = subprocess.run(command, check=True, capture_output=True, text=True, env=environment)

    return [
        cast(dict[str, object], json.loads(line)) for line in result.stdout.splitlines() if line
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    arguments = parser.parse_args()

    ranked = rank(arguments.database_url, arguments.limit)
    json.dump({"candidates": ranked, "ranked": len(ranked)}, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
