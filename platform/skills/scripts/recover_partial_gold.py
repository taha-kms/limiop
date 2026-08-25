"""Recover still-live gold postings into the ignored measurement workspace."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlparse

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SAMPLE = REPOSITORY_ROOT / "docs/skill-model-measurement/sample.json"
DEFAULT_DESTINATION = REPOSITORY_ROOT / ".research/platform-skills-recovered-postings.json"

CATALOG_QUERY = """
select json_build_object(
  'posting', s.key || ':' || p.source_job_id,
  'description', j.description
)::text
from jobs j
join job_provenance p on p.job_id = j.id
join job_sources s on s.id = p.source_id
order by s.key, p.source_job_id
"""


def _object(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(dict[str, object], value)


def _array(value: object, *, context: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")
    return cast(list[object], value)


def _string(value: object, *, context: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a string")
    return value


def expected_postings(sample_path: Path) -> set[tuple[str, str]]:
    document_value: object = json.loads(sample_path.read_text(encoding="utf-8"))
    document = _object(document_value, context=str(sample_path))
    rows = _array(document.get("sample"), context=f"{sample_path}: sample")
    expected: set[tuple[str, str]] = set()
    for index, value in enumerate(rows):
        row = _object(value, context=f"{sample_path}: sample[{index}]")
        expected.add(
            (
                _string(row.get("posting"), context=f"{sample_path}: sample[{index}].posting"),
                _string(
                    row.get("description_sha256"),
                    context=f"{sample_path}: sample[{index}].description_sha256",
                ),
            )
        )
    return expected


def psql_connection(database_url: str) -> tuple[list[str], dict[str, str]]:
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


def recover(database_url: str, sample_path: Path) -> list[dict[str, str]]:
    expected = expected_postings(sample_path)
    command, environment = psql_connection(database_url)
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    recovered: list[dict[str, str]] = []
    for line_number, line in enumerate(result.stdout.splitlines(), start=1):
        if not line:
            continue
        value: object = json.loads(line)
        row = _object(value, context=f"psql output line {line_number}")
        posting = _string(row.get("posting"), context=f"psql output line {line_number}.posting")
        description = _string(
            row.get("description"), context=f"psql output line {line_number}.description"
        )
        digest = hashlib.sha256(description.encode()).hexdigest()
        if (posting, digest) in expected:
            recovered.append(
                {
                    "posting": posting,
                    "description_sha256": digest,
                    "description": description,
                }
            )
    return recovered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recover hash-matched gold postings from the live SkillSync catalog."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("SKILLSYNC_DATABASE_URL"),
        help="defaults to SKILLSYNC_DATABASE_URL",
    )
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    arguments = parser.parse_args()
    if arguments.database_url is None:
        parser.error("--database-url or SKILLSYNC_DATABASE_URL is required")

    postings = recover(arguments.database_url, arguments.sample)
    payload = {
        "measurement": "platform-skills partial sanity check",
        "recovery": "live SkillSync catalog joined by posting key and description_sha256",
        "postings": postings,
    }
    arguments.destination.parent.mkdir(parents=True, exist_ok=True)
    arguments.destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "measurement": "partial sanity check",
                "recovered_postings": len(postings),
                "destination": str(arguments.destination),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
