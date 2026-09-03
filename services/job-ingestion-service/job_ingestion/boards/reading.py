"""Reading a JSON board response without trusting it.

Every JSON provider asks the same three questions of a body: is it JSON, is it
an object, is this an array of objects. The answers, and the words used when
the answer is no, are kept here so every provider reports the same failure
the same way.
"""

from typing import Any

import httpx2

from job_ingestion.contracts import RawRecord
from job_ingestion.errors import SourceResponseError


def json_body(source_key: str, slug: str, response: httpx2.Response) -> Any:
    try:
        return response.json()
    except ValueError as error:
        raise SourceResponseError(source_key, f"board {slug} is not valid JSON: {error}") from error


def json_object(source_key: str, slug: str, response: httpx2.Response) -> dict[str, Any]:
    body = json_body(source_key, slug, response)
    if not isinstance(body, dict):
        raise SourceResponseError(source_key, f"board {slug} is not a JSON object")
    return body


def record_list(source_key: str, slug: str, value: object, *, name: str) -> tuple[RawRecord, ...]:
    """The records under one key, each of which must be an object."""
    if not isinstance(value, list):
        raise SourceResponseError(source_key, f"board {slug} has no {name} array")
    records: list[RawRecord] = []
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise SourceResponseError(
                source_key, f"board {slug} record {index} is not a JSON object"
            )
        records.append(record)
    return tuple(records)
