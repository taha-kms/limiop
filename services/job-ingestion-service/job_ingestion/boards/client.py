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
from job_ingestion.boards.reading import json_object
from job_ingestion.contracts import IngestionStage, RawPage, RawRecord, RecordFailure
from job_ingestion.errors import SourceResponseError, SourceUnavailableError
from job_ingestion.transport import retrying_get


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


@dataclass(frozen=True, slots=True)
class BoardOutcome:
    """What happened to one configured board during a walk.

    `records` is the count read on success, or `None` when the board could
    not be read at all. A board whose hydration dropped a record still
    counts as read: the drop is already a record failure and denies
    `reached_the_end`, but the board itself answered, so it is not a
    fetch failure here.
    """

    slug: str
    records: int | None
    failure: str | None


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
        # One entry per configured board, in configuration order, reset at
        # the start of each walk. This is what the pipeline hands to the
        # registry so a poll's result reaches the board it was about, not
        # just the source as a whole.
        self.outcomes: list[BoardOutcome] = []
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

        The retry loop -- transport failures and rate limits, at most
        `max_attempts` times -- lives in `job_ingestion.transport.retrying_get`,
        shared with every other client here. Any other answer is returned as
        it is: a board that answers is answering, and asking again will not
        change what it said. A rate limit is the exception, because it is a
        request to wait rather than a refusal.
        """
        return await retrying_get(
            self._http_client,
            request.url,
            params=request.params,
            headers=request.headers,
            timeout_seconds=self.config.timeout_seconds,
            max_attempts=self.config.max_attempts,
            retry_backoff_seconds=self.config.retry_backoff_seconds,
            sleeper=self.sleeper,
            source_key=self.source_key,
            subject=f"board {slug}",
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

        if self.provider.detail_request is not None:
            records = await self.hydrate(slug, records)
        return RawPage(records=tuple(records), next_page=None)

    async def hydrate(self, slug: str, records: list[RawRecord]) -> list[RawRecord]:
        """Merge each record with the detail the provider asks for.

        Order is the listing's. A record whose detail cannot be read is
        dropped rather than passed on without it, because a posting without
        its text cannot be normalized and would only fail later with a less
        useful reason. The drop is recorded as a fetch failure, and the board
        is no longer fully read: reconciliation must not conclude the posting
        is gone.
        """
        detail_request = self.provider.detail_request
        assert detail_request is not None
        semaphore = asyncio.Semaphore(self.config.detail_concurrency)

        async def one(record: RawRecord) -> RawRecord | RecordFailure:
            request = detail_request(self.base_url, record)
            if request is None:
                return record
            async with semaphore:
                try:
                    response = await self.request(slug, request)
                    if response.status_code != httpx2.codes.OK:
                        raise SourceResponseError(
                            self.source_key,
                            f"board {slug} returned status {response.status_code}",
                            status_code=response.status_code,
                        )
                    detail = json_object(self.source_key, slug, response)
                except (SourceResponseError, SourceUnavailableError) as error:
                    return RecordFailure(
                        stage=IngestionStage.FETCH,
                        reason=f"posting detail could not be read: {error.message}",
                        source_job_id=self._identifier(slug, record),
                    )
            return {**record, **detail}

        hydrated: list[RawRecord] = []
        for outcome in await asyncio.gather(*(one(record) for record in records)):
            if isinstance(outcome, RecordFailure):
                self._dropped_a_record = True
                self.failures.append(outcome)
            else:
                hydrated.append(outcome)
        return hydrated

    @staticmethod
    def _identifier(slug: str, record: RawRecord) -> str | None:
        identifier = record.get("id")
        if isinstance(identifier, int | str) and str(identifier).strip():
            return f"{slug}:{identifier}"
        return None

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        """Yield one page per board, skipping boards that cannot be read.

        A board is an independent company. One of them going away says nothing
        about the others, so its failure is recorded and the run continues.

        Each walk reports its own failures: `failures` is reset here along with
        the other per-walk state, so a second walk over the same client does not
        carry forward what the first one recorded.
        """
        self._reached_the_end = False
        self._dropped_a_record = False
        self.failures = []
        self.outcomes = []
        skipped = False
        for board in self.config.boards:
            try:
                page = await self.fetch_board(board)
            except (SourceResponseError, SourceUnavailableError) as error:
                skipped = True
                self.failures.append(
                    RecordFailure(stage=IngestionStage.FETCH, reason=error.message)
                )
                self.outcomes.append(BoardOutcome(board, None, error.message))
            else:
                self.outcomes.append(BoardOutcome(board, len(page.records), None))
                yield page
        self._reached_the_end = not skipped and not self._dropped_a_record
