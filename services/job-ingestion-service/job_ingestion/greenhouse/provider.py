"""Greenhouse as a tenant-board provider.

A board answers a single request with everything it has, so there is no
pagination. Descriptions come only when asked for, and a posting without one
cannot be normalized. Every posting states the company its board belongs to,
which is what lets discovery confirm a guessed slug.
"""

from collections.abc import Sequence

import httpx2

from job_ingestion.boards.provider import BoardProvider, PageRead, Request
from job_ingestion.boards.reading import json_object, record_list
from job_ingestion.contracts import RawRecord
from job_ingestion.greenhouse.normalizer import GreenhouseNormalizer
from job_ingestion.greenhouse.records import GreenhouseJobRecord, GreenhouseValidator
from job_ingestion.greenhouse.source import (
    DEFAULT_BASE_URL,
    DEFAULT_BOARDS,
    DISPLAY_NAME,
    PRECEDENCE,
    SOURCE_KEY,
)


def board_request(base_url: str, slug: str, _cursor: object | None) -> Request:
    return Request(url=f"{base_url.rstrip('/')}/{slug}/jobs", params={"content": "true"})


def read_page(slug: str, response: httpx2.Response) -> PageRead:
    body = json_object(SOURCE_KEY, slug, response)
    return PageRead(records=record_list(SOURCE_KEY, slug, body.get("jobs"), name="jobs"))


def stated_company(records: Sequence[RawRecord]) -> str | None:
    """The company a board says its postings belong to."""
    for record in records:
        stated = record.get("company_name")
        if isinstance(stated, str) and stated.strip():
            return stated
    return None


GREENHOUSE: BoardProvider[GreenhouseJobRecord] = BoardProvider(
    source_key=SOURCE_KEY,
    display_name=DISPLAY_NAME,
    precedence=PRECEDENCE,
    default_base_url=DEFAULT_BASE_URL,
    default_boards=DEFAULT_BOARDS,
    validator=GreenhouseValidator(),
    normalizer=GreenhouseNormalizer(),
    board_request=board_request,
    read_page=read_page,
    stated_company=stated_company,
)
