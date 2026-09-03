"""HTTP access to any provider shaped as one board per tenant.

Transport only. Returns untrusted provider payloads and never inspects a job
field, so validation and normalization stay testable without a network.

One source, many boards. A board is where a company publishes; the provider
is the system it publishes on. Each board becomes one page, whatever number
of requests it took to read, because the run and reconciliation reason about
boards rather than requests.

Which boards to read is configured. Finding them is a separate problem, because
a wrong guess ingests one company's postings under another company's name.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

import httpx2

from job_ingestion.boards.provider import BoardProvider, Request
from job_ingestion.contracts import IngestionStage, RawPage, RawRecord, RecordFailure
from job_ingestion.errors import SourceResponseError, SourceUnavailableError
from job_ingestion.rate_limit import is_rate_limited, retry_delay


@dataclass(frozen=True, slots=True)
class BoardConfig:
    """Bounded transport settings and the boards to read.

    `base_url` of `None` means the provider's own. It is a setting at all so a
    deployment can read a provider's regional host without a code change.
    """

    boards: tuple[str, ...] = ()
    base_url: str | None = None
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.5
    # A board that keeps answering with a next page is a provider bug or a
    # loop, and either way not something to walk without end.
    max_pages_per_board: int = 100
    detail_concurrency: int = 4

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")
        if self.max_pages_per_board < 1:
            raise ValueError("max_pages_per_board must be at least 1")
        if self.detail_concurrency < 1:
            raise ValueError("detail_concurrency must be at least 1")
        for board in self.boards:
            if not board.strip():
                raise ValueError("a board name must not be blank")


@dataclass
class BoardClient:
    """Fetches untrusted postings from every configured board of one provider."""

    provider: BoardProvider[Any]
    config: BoardConfig = field(default_factory=BoardConfig)
    http_client: httpx2.AsyncClient | None = None
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep

    def __post_init__(self) -> None:
        self._owns_http_client = self.http_client is None
        self._http_client = (
            self.http_client
            if self.http_client is not None
            else httpx2.AsyncClient(timeout=self.config.timeout_seconds)
        )
        # Boards that could not be read. Collected rather than raised, so one
        # unreachable company does not discard every other company's postings,
        # and reported afterwards so it is not lost either.
        self.failures: list[RecordFailure] = []
        self._reached_the_end = False
        self._dropped_a_record = False

    @property
    def source_key(self) -> str:
        return self.provider.source_key

    @property
    def base_url(self) -> str:
        return self.config.base_url or self.provider.default_base_url

    @property
    def reached_the_end(self) -> bool:
        """Whether every configured board was read in full.

        A board that could not be read leaves that company's postings unseen,
        and an unseen posting is indistinguishable from one that is gone, so a
        single skipped board denies the whole run. So does a single posting
        whose detail could not be read.
        """
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

    async def request(self, slug: str, request: Request) -> httpx2.Response:
        """Make one request, retrying what may succeed later.

        Retries transport failures and rate limits, at most `max_attempts`
        times. Any other answer is returned as it is: a board that answers is
        answering, and asking again will not change what it said. A rate
        limit is the exception, because it is a request to wait rather than a
        refusal.
        """
        last_failure: SourceUnavailableError | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            delay = self.config.retry_backoff_seconds
            try:
                response = await self._http_client.get(
                    request.url,
                    params=dict(request.params),
                    timeout=self.config.timeout_seconds,
                )
            except httpx2.TimeoutException as error:
                last_failure = SourceUnavailableError(
                    self.source_key, f"board {slug} timed out: {error}"
                )
            except httpx2.TransportError as error:
                last_failure = SourceUnavailableError(
                    self.source_key, f"board {slug} could not be reached: {error}"
                )
            else:
                if not is_rate_limited(response):
                    return response
                last_failure = SourceUnavailableError(
                    self.source_key, f"board {slug} was rate limited"
                )
                delay = retry_delay(response, fallback=delay)

            if attempt < self.config.max_attempts:
                await self.sleeper(delay)

        raise (
            last_failure
            if last_failure is not None
            else SourceUnavailableError(self.source_key, f"board {slug} could not be fetched")
        )

    async def fetch_board(self, slug: str) -> RawPage:
        """Return every posting on one board, however many pages it takes."""
        records: list[RawRecord] = []
        cursor: object | None = None
        for _ in range(self.config.max_pages_per_board):
            response = await self.request(
                slug, self.provider.board_request(self.base_url, slug, cursor)
            )
            if response.status_code != httpx2.codes.OK:
                raise SourceResponseError(
                    self.source_key,
                    f"board {slug} returned status {response.status_code}",
                    status_code=response.status_code,
                )
            page = self.provider.read_page(slug, response)
            # The board is stamped on the record because a posting identifier
            # is only unique within its own board, and provenance needs one
            # that is unique within the source.
            records.extend({**record, "board": slug} for record in page.records)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        else:
            raise SourceResponseError(
                self.source_key,
                f"board {slug} did not end within {self.config.max_pages_per_board} pages",
            )

        return RawPage(records=tuple(records), next_page=None)

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        """Yield one page per board, skipping boards that cannot be read.

        A board is an independent company. One of them going away says nothing
        about the others, so its failure is recorded and the run continues.
        """
        self._reached_the_end = False
        self._dropped_a_record = False
        skipped = False
        for board in self.config.boards:
            try:
                yield await self.fetch_board(board)
            except (SourceResponseError, SourceUnavailableError) as error:
                skipped = True
                self.failures.append(
                    RecordFailure(stage=IngestionStage.FETCH, reason=error.message)
                )
        self._reached_the_end = not skipped and not self._dropped_a_record
