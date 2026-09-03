"""Polymer as a tenant-board provider.

A board is walked page by page, and a request past the last one still comes
back with a next page advertised, so the walk also ends on an empty page.
Listings omit the description, so every posting is hydrated with a second
request before it can be normalized. Every posting states the company its
board belongs to, which is what lets discovery confirm a guessed slug.
"""

from collections.abc import Sequence

import httpx2

from job_ingestion.boards.provider import BoardProvider, PageRead, Request
from job_ingestion.boards.reading import json_object, record_list
from job_ingestion.contracts import RawRecord
from job_ingestion.polymer.normalizer import PolymerNormalizer
from job_ingestion.polymer.records import PolymerJobRecord, PolymerValidator
from job_ingestion.polymer.source import (
    DEFAULT_BASE_URL,
    DEFAULT_BOARDS,
    DISPLAY_NAME,
    PRECEDENCE,
    SOURCE_KEY,
)


def board_request(base_url: str, slug: str, cursor: object | None) -> Request:
    page = cursor if isinstance(cursor, int) else 1
    return Request(url=f"{base_url.rstrip('/')}/{slug}/jobs", params={"page": str(page)})


def read_page(slug: str, response: httpx2.Response) -> PageRead:
    body = json_object(SOURCE_KEY, slug, response)
    records = record_list(SOURCE_KEY, slug, body.get("items"), name="items")
    meta = body.get("meta")
    next_page = meta.get("next_page") if isinstance(meta, dict) else None
    # An empty page past the end still advertises a next page, so the walk
    # ends on emptiness as well as on the provider saying so.
    return PageRead(
        records=records, next_cursor=next_page if records and isinstance(next_page, int) else None
    )


def stated_company(records: Sequence[RawRecord]) -> str | None:
    """The company a board says its postings belong to."""
    for record in records:
        stated = record.get("organization_name")
        if isinstance(stated, str) and stated.strip():
            return stated
    return None


def detail_request(record: RawRecord) -> Request | None:
    board, identifier = record.get("board"), record.get("id")
    if not isinstance(board, str) or not isinstance(identifier, int):
        return None
    # The hook sees only the record, so the provider's own host is used;
    # Polymer has one host.
    return Request(url=f"{DEFAULT_BASE_URL}/{board}/jobs/{identifier}")


POLYMER: BoardProvider[PolymerJobRecord] = BoardProvider(
    source_key=SOURCE_KEY,
    display_name=DISPLAY_NAME,
    precedence=PRECEDENCE,
    default_base_url=DEFAULT_BASE_URL,
    default_boards=DEFAULT_BOARDS,
    validator=PolymerValidator(),
    normalizer=PolymerNormalizer(),
    board_request=board_request,
    read_page=read_page,
    stated_company=stated_company,
    detail_request=detail_request,
)
