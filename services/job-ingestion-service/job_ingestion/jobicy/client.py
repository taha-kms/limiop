"""HTTP access to the Jobicy remote-jobs API.

This module owns transport only. It returns untrusted provider payloads and
never inspects a job field, so validation and normalization stay testable
without a network.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Self

import httpx2

from job_ingestion.contracts import RawPage, RawRecord
from job_ingestion.errors import SourceResponseError, SourceUnavailableError
from job_ingestion.rate_limit import is_rate_limited, retry_delay

SOURCE_KEY = "jobicy"
DEFAULT_BASE_URL = "https://jobicy.com/api/v2/remote-jobs"
MAX_COUNT = 200

# Jobicy asks that the feed be credited, and a descriptive agent is how a
# provider tells a scraper from a build asking for a documented amount of
# public data on a schedule it also documents.
USER_AGENT = "SkillSync/0.1 (job aggregation; https://github.com/taha-kms/limiop)"


@dataclass(frozen=True, slots=True)
class JobicyConfig:
    """Bounded transport settings.

    There is no `max_pages` here because there is no pagination: the feed
    returns everything asked for in one request, bounded instead by `count`.
    """

    base_url: str = DEFAULT_BASE_URL
    count: int = MAX_COUNT
    timeout_seconds: float = 10.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if not 1 <= self.count <= MAX_COUNT:
            raise ValueError(f"count must be between 1 and {MAX_COUNT}")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")


class JobicyClient:
    """Fetches the untrusted feed page from Jobicy."""

    def __init__(
        self,
        config: JobicyConfig | None = None,
        *,
        http_client: httpx2.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config if config is not None else JobicyConfig()
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
        """Whether the last walk read the feed, rather than failing before it."""
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

    async def fetch_page(self) -> RawPage:
        """Return the feed's one page of untrusted records.

        Retries transport failures and rate limits, at most `max_attempts`
        times, the same policy `arbeitnow.client` uses and for the same
        reason: a rate limit is the most predictable non-200 a public API
        returns.
        """
        last_failure: SourceUnavailableError | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            delay = self.config.retry_backoff_seconds
            try:
                response = await self._http_client.get(
                    self.config.base_url,
                    params={"count": str(self.config.count)},
                    timeout=self.config.timeout_seconds,
                    headers={"User-Agent": USER_AGENT},
                )
            except httpx2.TimeoutException as error:
                last_failure = SourceUnavailableError(SOURCE_KEY, f"the feed timed out: {error}")
            except httpx2.TransportError as error:
                last_failure = SourceUnavailableError(
                    SOURCE_KEY, f"the feed could not be reached: {error}"
                )
            else:
                if not is_rate_limited(response):
                    return self._read_page(response)
                last_failure = SourceUnavailableError(SOURCE_KEY, "the feed was rate limited")
                delay = retry_delay(response, fallback=delay)

            if attempt < self.config.max_attempts:
                await self._sleeper(delay)

        raise (
            last_failure
            if last_failure is not None
            else SourceUnavailableError(SOURCE_KEY, "the feed could not be fetched")
        )

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        """Yield the feed's one page.

        There is nothing to walk: `count` is the whole request. `reached_the_end`
        only becomes true once that page is actually read, so a failed fetch
        still reports, correctly, that it did not see everything.
        """
        self._reached_the_end = False
        fetched = await self.fetch_page()
        yield fetched
        self._reached_the_end = True

    def _read_page(self, response: httpx2.Response) -> RawPage:
        if response.status_code != httpx2.codes.OK:
            raise SourceResponseError(
                SOURCE_KEY,
                f"the feed returned status {response.status_code}",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as error:
            raise SourceResponseError(SOURCE_KEY, f"the feed is not valid JSON: {error}") from error

        if not isinstance(body, dict):
            raise SourceResponseError(SOURCE_KEY, "the feed is not a JSON object")

        records = body.get("jobs")
        if not isinstance(records, list):
            raise SourceResponseError(SOURCE_KEY, "the feed has no jobs array")

        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise SourceResponseError(SOURCE_KEY, f"record {index} is not a JSON object")

        return RawPage(records=tuple[RawRecord, ...](records), next_page=None)
