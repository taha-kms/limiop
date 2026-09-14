"""What one tenant-board provider has to say about itself.

A provider is a value, not a class to inherit from. The client reads it; the
provider never sees the client. That keeps every provider-specific decision in
one place and every shared one out of it.

The stage contracts for validation and normalization are the ones in
`contracts.py`. This module adds only what the client needs to fetch and to
verify a board, which those contracts deliberately do not cover.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx2
from platform_db.models import Company

from job_ingestion.boards.discovery import DiscoveryOutcome
from job_ingestion.contracts import JobRecordNormalizer, JobRecordValidator, RawRecord

if TYPE_CHECKING:
    from job_ingestion.boards.client import BoardClient


@dataclass(frozen=True, slots=True)
class Request:
    """One HTTP GET the client should make.

    `headers` defaults to empty for every ordinary board and detail request;
    it exists for the one case that needs it — a verifier reaching a host
    the client was not configured for, which identifies itself rather than
    riding on whatever default the transport happens to send.
    """

    url: str
    params: Mapping[str, str] = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)


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
class Verification:
    """What a provider's own `verify` learned about a board beyond its feed.

    `outcome` is one of `CONFIRMED`, `NAMED`, `WRONG_COMPANY`, or
    `UNVERIFIABLE` — the same vocabulary `discover()` reports, so the
    registry writes both through one switch. `evidence` is stored on the row
    exactly as given; its `kind` says which check produced it.

    `slug`, when set, means the verifier learned a board the guess did not
    name — a link or redirect to a different subdomain than the one being
    checked. The registry keys the row on this slug instead of the guessed
    one. `None`, the default, is every verifier's answer about the slug it
    was actually asked about.
    """

    outcome: DiscoveryOutcome
    found_company: str | None
    evidence: dict[str, object]
    slug: str | None = None


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

    `verify(client, slug, company)`, when present, is called by discovery
    when the feed itself states nothing (`discover()` reported
    `UNVERIFIABLE`). It looks beyond the feed — a careers site's own title,
    a link on the company's website — for evidence the feed cannot give.
    Absent, an unverifiable guess just stays unverifiable, as it always has.

    `locate(client, company)`, when present, is called by discovery when NO
    guess answered at all (`discover()` reported `NOT_FOUND`), to ask the
    company's own website whether it names a board this provider hosts,
    without a guessed slug to check against. Returns a `Verification` with
    `slug` set, naming the board it found, or `None`. Absent, a not-found
    guess just stays not-found, as it always has.
    """

    source_key: str
    display_name: str
    precedence: int
    default_base_url: str
    validator: JobRecordValidator[ProviderRecordT]
    normalizer: JobRecordNormalizer[ProviderRecordT]
    board_request: Callable[[str, str, object | None], Request]
    read_page: Callable[[str, httpx2.Response], PageRead]
    stated_company: Callable[[Sequence[RawRecord]], str | None]
    detail_request: Callable[[str, RawRecord], Request | None] | None = None
    verify: Callable[["BoardClient", str, Company], Awaitable[Verification]] | None = None
    locate: Callable[["BoardClient", Company], Awaitable[Verification | None]] | None = None
