"""What one tenant-board provider has to say about itself.

A provider is a value, not a class to inherit from. The client reads it; the
provider never sees the client. That keeps every provider-specific decision in
one place and every shared one out of it.

The stage contracts for validation and normalization are the ones in
`contracts.py`. This module adds only what the client needs to fetch and to
verify a board, which those contracts deliberately do not cover.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import httpx2

from job_ingestion.contracts import JobRecordNormalizer, JobRecordValidator, RawRecord


@dataclass(frozen=True, slots=True)
class Request:
    """One HTTP GET the client should make."""

    url: str
    params: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PageRead:
    """What one response held, and how to ask for the rest.

    `next_cursor` is whatever the provider needs to ask for the next page: an
    offset, a page number, a token. `None` means there is no next page. What
    the value is belongs to the provider and the client never inspects it.
    """

    records: tuple[RawRecord, ...]
    next_cursor: object | None = None


@dataclass(frozen=True, slots=True)
class BoardProvider[ProviderRecordT]:
    """Everything that differs between one tenant-board provider and another.

    `board_request(base_url, slug, cursor)` names the request for one page of
    one board. The first call passes `cursor=None`.

    `read_page(slug, response)` turns a successful response into records and
    the next cursor, or raises `SourceResponseError` when the body is not the
    documented shape. The client has already checked the status code. This is
    where a JSON key is chosen or an XML element is walked; it must not
    inspect job fields, which is validation's job.

    `stated_company(records)` is the company a board says its postings belong
    to, or `None` when the feed never says. Discovery reads it to confirm a
    guessed slug. A provider that cannot state one makes every guess
    unverifiable, and discovery reports that rather than confirming anything.

    `detail_request(base_url, record)`, when present, names a second request
    whose JSON object body is merged over the listing record before
    validation. For providers whose listing omits the description. The
    configured host is passed so a regional override reaches detail requests
    as well as listing requests.
    """

    source_key: str
    display_name: str
    precedence: int
    default_base_url: str
    default_boards: tuple[str, ...]
    validator: JobRecordValidator[ProviderRecordT]
    normalizer: JobRecordNormalizer[ProviderRecordT]
    board_request: Callable[[str, str, object | None], Request]
    read_page: Callable[[str, httpx2.Response], PageRead]
    stated_company: Callable[[Sequence[RawRecord]], str | None]
    detail_request: Callable[[str, RawRecord], Request | None] | None = None
