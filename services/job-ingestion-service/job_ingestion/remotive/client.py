"""HTTP access to the Remotive remote job API.

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

SOURCE_KEY = "remotive"
DEFAULT_BASE_URL = "https://remotive.com/api/remote-jobs"

# The other clients in this service leave the default httpx2 user agent in
# place; none of them has been asked to identify itself. Remotive's own notice
# asks callers to poll no more than four times a day, and naming the caller is
# what makes that ask enforceable against a specific integration rather than
# against undifferentiated traffic.
USER_AGENT = "SkillSync/0.1 (job aggregation; https://github.com/taha-kms/limiop)"


@dataclass(frozen=True, slots=True)
class RemotiveConfig:
    """Bounded transport settings.

    Every limit has a finite default. Remotive has no pagination -- one
    request returns everything the feed carries -- so there is no `max_pages`
    here the way the paginated clients need one; `max_attempts` still bounds
    retrying that single request.
    """

    base_url: str = DEFAULT_BASE_URL
    # Sent as the `limit` query parameter only when set. Remotive returns
    # everything it has when it is left out, so a caller opts into narrowing
    # the response rather than the client guessing at a default worth sending.
    limit: int | None = None
    timeout_seconds: float = 10.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.limit is not None and self.limit < 1:
            raise ValueError("limit must be at least 1")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")


class RemotiveClient:
    """Fetches the one untrusted page Remotive has to offer."""

    def __init__(
        self,
        config: RemotiveConfig | None = None,
        *,
        http_client: httpx2.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config if config is not None else RemotiveConfig()
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
        """Whether the last walk read the one page Remotive has to offer,
        rather than stopping on a failure before it could."""
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
        """Return the one page of untrusted records Remotive has to offer.

        Retries transport failures and rate limits, at most `max_attempts`
        times, the same shape every other client here follows. Remotive has no
        pagination, so this single request is also everything a walk will ever
        fetch.

        Exhausting the attempts still raises, so a truncated read reports
        `reached_the_end: false` and may not withdraw what it never saw.
        """
        last_failure: SourceUnavailableError | None = None
        params: dict[str, int] = {}
        if self.config.limit is not None:
            params["limit"] = self.config.limit

        for attempt in range(1, self.config.max_attempts + 1):
            delay = self.config.retry_backoff_seconds
            try:
                response = await self._http_client.get(
                    self.config.base_url,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=self.config.timeout_seconds,
                )
            except httpx2.TimeoutException as error:
                last_failure = SourceUnavailableError(SOURCE_KEY, f"request timed out: {error}")
            except httpx2.TransportError as error:
                last_failure = SourceUnavailableError(
                    SOURCE_KEY, f"request could not be reached: {error}"
                )
            else:
                if not is_rate_limited(response):
                    return self._read_page(response)
                last_failure = SourceUnavailableError(SOURCE_KEY, "request was rate limited")
                delay = retry_delay(response, fallback=delay)

            if attempt < self.config.max_attempts:
                await self._sleeper(delay)

        raise (
            last_failure
            if last_failure is not None
            else SourceUnavailableError(SOURCE_KEY, "request could not be fetched")
        )

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        """Yield the one page Remotive has, then report the walk complete.

        There is nothing to page through, so a successful fetch is the whole
        walk: `reached_the_end` is set only once `fetch_page` has returned, the
        same rule every paginated client here follows at the end of its walk.
        """
        self._reached_the_end = False
        page = await self.fetch_page()
        yield page
        self._reached_the_end = True

    def _read_page(self, response: httpx2.Response) -> RawPage:
        if response.status_code != httpx2.codes.OK:
            raise SourceResponseError(
                SOURCE_KEY,
                f"request returned status {response.status_code}",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as error:
            raise SourceResponseError(SOURCE_KEY, f"response is not valid JSON: {error}") from error

        if not isinstance(body, dict):
            raise SourceResponseError(SOURCE_KEY, "response is not a JSON object")

        records = body.get("jobs")
        if not isinstance(records, list):
            raise SourceResponseError(SOURCE_KEY, "response has no jobs array")

        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise SourceResponseError(SOURCE_KEY, f"record {index} is not a JSON object")

        return RawPage(records=tuple[RawRecord, ...](records), next_page=None)
