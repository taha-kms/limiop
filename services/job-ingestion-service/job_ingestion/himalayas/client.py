"""HTTP access to the Himalayas job board API.

This module owns transport only. It returns untrusted provider payloads and
never inspects a job field, so validation and normalization stay testable
without a network.

Himalayas pages by cursor rather than by number: each response carries a
`nextCursor` that must be sent back verbatim as `?cursor=` to read the
following page, and `nextCursor` is `null` on the last one. `RawPage.next_page`
is typed `int | None` for providers that page by number, so the cursor is kept
inside this client rather than forced through that type. `fetch_page` returns
the provider's own cursor value alongside the page's records, and `fetch_pages`
tracks it across the walk; every yielded `RawPage` reports `next_page=None`,
the same way `boards/client.py::fetch_board` walks a provider cursor without
exposing it.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx2

from job_ingestion.contracts import RawPage, RawRecord
from job_ingestion.errors import SourceResponseError, SourceUnavailableError
from job_ingestion.rate_limit import is_rate_limited, retry_delay

SOURCE_KEY = "himalayas"
DEFAULT_BASE_URL = "https://himalayas.app/jobs/api"

# The API accepts a page size of at most 20 records.
MAX_LIMIT = 20


@dataclass(frozen=True, slots=True)
class HimalayasConfig:
    """Bounded transport settings.

    Every limit has a finite default. `max_pages` and `max_attempts` exist so
    neither pagination nor retrying can run without an end: the feed holds
    roughly 100,000 postings, so an unbounded walk is not an option.
    """

    base_url: str = DEFAULT_BASE_URL
    limit: int = MAX_LIMIT
    timeout_seconds: float = 10.0
    max_pages: int = 25
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")


class HimalayasClient:
    """Fetches untrusted pages from Himalayas."""

    def __init__(
        self,
        config: HimalayasConfig | None = None,
        *,
        http_client: httpx2.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config if config is not None else HimalayasConfig()
        self._owns_http_client = http_client is None
        self._http_client = (
            http_client
            if http_client is not None
            else httpx2.AsyncClient(timeout=self.config.timeout_seconds)
        )
        self._sleeper = sleeper
        self._reached_the_end = False

    @property
    def source_key(self) -> str:
        return SOURCE_KEY

    @property
    def reached_the_end(self) -> bool:
        """Whether the last walk ran out of pages rather than out of allowance."""
        return self._reached_the_end

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client if this client created it."""
        if self._owns_http_client:
            await self._http_client.aclose()

    async def fetch_page(self, cursor: str | None) -> tuple[tuple[RawRecord, ...], str | None]:
        """Return one page of untrusted records and the cursor for the next.

        Retries transport failures and rate limits, at most `max_attempts`
        times. A rate limit is transient by definition and is the most
        predictable non-200 a public API returns, which made it the one
        transient failure that used to end a run where it stood.

        Exhausting the attempts still raises, so a truncated read reports
        `reached_the_end: false` and may not withdraw what it never saw.
        """
        label = "the first page" if cursor is None else f"the page after cursor {cursor!r}"
        params: dict[str, str] = {"limit": str(self.config.limit)}
        if cursor is not None:
            params["cursor"] = cursor

        last_failure: SourceUnavailableError | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            delay = self.config.retry_backoff_seconds
            try:
                response = await self._http_client.get(
                    self.config.base_url,
                    params=params,
                    timeout=self.config.timeout_seconds,
                )
            except httpx2.TimeoutException as error:
                last_failure = SourceUnavailableError(SOURCE_KEY, f"{label} timed out: {error}")
            except httpx2.TransportError as error:
                last_failure = SourceUnavailableError(
                    SOURCE_KEY, f"{label} could not be reached: {error}"
                )
            else:
                if not is_rate_limited(response):
                    return self._read_page(label, response)
                last_failure = SourceUnavailableError(SOURCE_KEY, f"{label} was rate limited")
                delay = retry_delay(response, fallback=delay)

            if attempt < self.config.max_attempts:
                await self._sleeper(delay)

        raise (
            last_failure
            if last_failure is not None
            else SourceUnavailableError(SOURCE_KEY, f"{label} could not be fetched")
        )

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        """Yield pages in order, stopping at the end of the feed or `max_pages`.

        The cursor is this method's own state, never the caller's: it starts
        at `None` for the first page and is replaced by whatever `fetch_page`
        reports until the feed reports none. Stopping at `max_pages` leaves the
        rest of the feed unread, which is not the same as there being no rest,
        so only the first exit reports the end.
        """
        self._reached_the_end = False
        cursor: str | None = None
        for _ in range(self.config.max_pages):
            records, next_cursor = await self.fetch_page(cursor)
            yield RawPage(records=records, next_page=None)
            if next_cursor is None:
                self._reached_the_end = True
                return
            cursor = next_cursor

    def _read_page(
        self, label: str, response: httpx2.Response
    ) -> tuple[tuple[RawRecord, ...], str | None]:
        if response.status_code != httpx2.codes.OK:
            raise SourceResponseError(
                SOURCE_KEY,
                f"{label} returned status {response.status_code}",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as error:
            raise SourceResponseError(SOURCE_KEY, f"{label} is not valid JSON: {error}") from error

        if not isinstance(body, dict):
            raise SourceResponseError(SOURCE_KEY, f"{label} is not a JSON object")

        records = body.get("jobs")
        if not isinstance(records, list):
            raise SourceResponseError(SOURCE_KEY, f"{label} has no jobs array")

        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise SourceResponseError(
                    SOURCE_KEY, f"{label} record {index} is not a JSON object"
                )

        return tuple[RawRecord, ...](records), self._read_next_cursor(body)

    @staticmethod
    def _read_next_cursor(body: dict[str, Any]) -> str | None:
        cursor = body.get("nextCursor")
        return cursor if isinstance(cursor, str) and cursor else None
