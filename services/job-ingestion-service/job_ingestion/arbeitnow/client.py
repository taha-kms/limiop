"""HTTP access to the Arbeitnow job board API.

This module owns transport only. It returns untrusted provider payloads and
never inspects a job field, so validation and normalization stay testable
without a network.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx2

from job_ingestion.contracts import RawPage, RawRecord
from job_ingestion.errors import SourceResponseError, SourceUnavailableError

SOURCE_KEY = "arbeitnow"
DEFAULT_BASE_URL = "https://www.arbeitnow.com/api/job-board-api"


@dataclass(frozen=True, slots=True)
class ArbeitnowConfig:
    """Bounded transport settings.

    Every limit has a finite default. `max_pages` and `max_attempts` exist so
    neither pagination nor retrying can run without an end.
    """

    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 10.0
    max_pages: int = 20
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")


class ArbeitnowClient:
    """Fetches untrusted pages from Arbeitnow."""

    def __init__(
        self,
        config: ArbeitnowConfig | None = None,
        *,
        http_client: httpx2.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config if config is not None else ArbeitnowConfig()
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

    async def fetch_page(self, page: int) -> RawPage:
        """Return one page of untrusted records.

        Retries only transport failures, at most `max_attempts` times.
        """
        last_failure: SourceUnavailableError | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                response = await self._http_client.get(
                    self.config.base_url,
                    params={"page": page},
                    timeout=self.config.timeout_seconds,
                )
            except httpx2.TimeoutException as error:
                last_failure = SourceUnavailableError(SOURCE_KEY, f"page {page} timed out: {error}")
            except httpx2.TransportError as error:
                last_failure = SourceUnavailableError(
                    SOURCE_KEY, f"page {page} could not be reached: {error}"
                )
            else:
                return self._read_page(page, response)

            if attempt < self.config.max_attempts:
                await self._sleeper(self.config.retry_backoff_seconds)

        raise (
            last_failure
            if last_failure is not None
            else SourceUnavailableError(SOURCE_KEY, f"page {page} could not be fetched")
        )

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        """Yield pages in order, stopping at the end of the board or `max_pages`.

        Stopping at `max_pages` leaves the rest of the board unread, which is
        not the same as there being no rest, so only the first exit reports the
        end.
        """
        self._reached_the_end = False
        page = 1
        for _ in range(self.config.max_pages):
            fetched = await self.fetch_page(page)
            yield fetched
            if fetched.next_page is None:
                self._reached_the_end = True
                return
            page = fetched.next_page

    def _read_page(self, page: int, response: httpx2.Response) -> RawPage:
        if response.status_code != httpx2.codes.OK:
            raise SourceResponseError(
                SOURCE_KEY,
                f"page {page} returned status {response.status_code}",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as error:
            raise SourceResponseError(
                SOURCE_KEY, f"page {page} is not valid JSON: {error}"
            ) from error

        if not isinstance(body, dict):
            raise SourceResponseError(SOURCE_KEY, f"page {page} is not a JSON object")

        records = body.get("data")
        if not isinstance(records, list):
            raise SourceResponseError(SOURCE_KEY, f"page {page} has no data array")

        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise SourceResponseError(
                    SOURCE_KEY, f"page {page} record {index} is not a JSON object"
                )

        return RawPage(
            records=tuple[RawRecord, ...](records),
            next_page=self._read_next_page(page, body),
        )

    def _read_next_page(self, page: int, body: dict[str, Any]) -> int | None:
        links = body.get("links")
        if not isinstance(links, dict) or not links.get("next"):
            return None
        return page + 1
