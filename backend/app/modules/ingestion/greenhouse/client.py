"""HTTP access to Greenhouse company job boards.

Transport only. Returns untrusted provider payloads and never inspects a job
field, so validation and normalization stay testable without a network.

One source, many boards. A board is where a company publishes; Greenhouse is
the provider. Each board answers a single request with everything it has, so
there is no pagination here, and each board becomes one page.

Which boards to read is configured. Finding them is a separate problem, because
a wrong guess ingests one company's postings under another company's name.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self

import httpx2

from app.modules.ingestion.contracts import IngestionStage, RawPage, RawRecord, RecordFailure
from app.modules.ingestion.errors import SourceResponseError, SourceUnavailableError

SOURCE_KEY = "greenhouse"
DEFAULT_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


@dataclass(frozen=True, slots=True)
class GreenhouseConfig:
    """Bounded transport settings and the boards to read."""

    boards: tuple[str, ...] = ()
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")
        for board in self.boards:
            if not board.strip():
                raise ValueError("a board name must not be blank")


@dataclass
class GreenhouseClient:
    """Fetches untrusted postings from every configured board."""

    config: GreenhouseConfig = field(default_factory=GreenhouseConfig)
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

    @property
    def source_key(self) -> str:
        return SOURCE_KEY

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

    def board_url(self, board: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{board}/jobs"

    async def fetch_board(self, board: str) -> RawPage:
        """Return every posting on one board.

        Retries only transport failures, at most `max_attempts` times. A board
        that answers with a non-success status is not retried: it is answering.
        """
        last_failure: SourceUnavailableError | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                response = await self._http_client.get(
                    self.board_url(board),
                    # Descriptions come only when asked for, and a posting
                    # without one cannot be normalized.
                    params={"content": "true"},
                    timeout=self.config.timeout_seconds,
                )
            except httpx2.TimeoutException as error:
                last_failure = SourceUnavailableError(
                    SOURCE_KEY, f"board {board} timed out: {error}"
                )
            except httpx2.TransportError as error:
                last_failure = SourceUnavailableError(
                    SOURCE_KEY, f"board {board} could not be reached: {error}"
                )
            else:
                return self._read_board(board, response)

            if attempt < self.config.max_attempts:
                await self.sleeper(self.config.retry_backoff_seconds)

        raise (
            last_failure
            if last_failure is not None
            else SourceUnavailableError(SOURCE_KEY, f"board {board} could not be fetched")
        )

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        """Yield one page per board, skipping boards that cannot be read.

        A board is an independent company. One of them going away says nothing
        about the others, so its failure is recorded and the run continues.
        """
        for board in self.config.boards:
            try:
                yield await self.fetch_board(board)
            except (SourceResponseError, SourceUnavailableError) as error:
                self.failures.append(
                    RecordFailure(stage=IngestionStage.FETCH, reason=error.message)
                )

    def _read_board(self, board: str, response: httpx2.Response) -> RawPage:
        if response.status_code != httpx2.codes.OK:
            raise SourceResponseError(
                SOURCE_KEY,
                f"board {board} returned status {response.status_code}",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as error:
            raise SourceResponseError(
                SOURCE_KEY, f"board {board} is not valid JSON: {error}"
            ) from error

        if not isinstance(body, dict):
            raise SourceResponseError(SOURCE_KEY, f"board {board} is not a JSON object")

        records = body.get("jobs")
        if not isinstance(records, list):
            raise SourceResponseError(SOURCE_KEY, f"board {board} has no jobs array")

        annotated: list[RawRecord] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise SourceResponseError(
                    SOURCE_KEY, f"board {board} record {index} is not a JSON object"
                )
            # The board is stamped on the record because a posting identifier is
            # only unique within its own board, and provenance needs one that is
            # unique within the source.
            annotated.append({**record, "board": board})

        return RawPage(records=tuple(annotated), next_page=None)
