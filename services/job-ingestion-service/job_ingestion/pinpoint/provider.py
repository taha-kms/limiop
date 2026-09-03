"""Pinpoint as a tenant-board provider.

One request per subdomain: no paging, and no hydration, because the listing
already carries the full posting text. The tenant is a subdomain of Pinpoint's
own host rather than a path segment, which is the one thing that makes this
provider's request shape different from every other board provider. No
posting ever states the company its board belongs to, so `stated_company`
answers nothing and discovery can only report a guessed slug as unverifiable,
never confirm it.
"""

from collections.abc import Sequence

import httpx2

from job_ingestion.boards.provider import BoardProvider, PageRead, Request
from job_ingestion.boards.reading import json_object, record_list
from job_ingestion.contracts import RawRecord
from job_ingestion.pinpoint.normalizer import PinpointNormalizer
from job_ingestion.pinpoint.records import PinpointJobRecord, PinpointValidator
from job_ingestion.pinpoint.source import (
    DEFAULT_BASE_URL,
    DEFAULT_BOARDS,
    DISPLAY_NAME,
    PRECEDENCE,
    SOURCE_KEY,
)


def board_request(base_url: str, slug: str, _cursor: object | None) -> Request:
    """One request per subdomain. The tenant is a subdomain rather than a path,
    so it is inserted after the scheme of whatever host is configured."""
    scheme, _, host = base_url.rstrip("/").partition("://")
    return Request(url=f"{scheme}://{slug}.{host}/postings.json")


def read_page(slug: str, response: httpx2.Response) -> PageRead:
    body = json_object(SOURCE_KEY, slug, response)
    return PageRead(records=record_list(SOURCE_KEY, slug, body.get("data"), name="data"))


def stated_company(_records: Sequence[RawRecord]) -> str | None:
    """The feed never says whose postings these are."""
    return None


PINPOINT: BoardProvider[PinpointJobRecord] = BoardProvider(
    source_key=SOURCE_KEY,
    display_name=DISPLAY_NAME,
    precedence=PRECEDENCE,
    default_base_url=DEFAULT_BASE_URL,
    default_boards=DEFAULT_BOARDS,
    validator=PinpointValidator(),
    normalizer=PinpointNormalizer(),
    board_request=board_request,
    read_page=read_page,
    stated_company=stated_company,
)
