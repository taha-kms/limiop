"""HTTP access to the Adzuna job search API.

This module owns transport only. It returns untrusted provider payloads and
never inspects a job field, so validation and normalization stay testable
without a network.

Adzuna pages by number within a country: `/{country}/search/{page}`, from page
one. A walk covers every configured country in order and at most
`pages_per_country` pages of each, leaving a country early when a page comes
back short, which is the only sign the API gives that it has nothing more to
say there. A result's `id` is unique only within its country, so every record
leaves here stamped with the country it was searched in.

Every request is windowed by `max_days_old`, so a short page means "nothing
more from the last few days", never "nothing more on the source". This client
therefore never reports `reached_the_end`: a walk that came up short in every
country still has not seen any posting older than the window, and the
lifecycle rule must not retire what a run never looked at.

Every page is one call against a licensed daily budget. The reservation is
made through `reserving_get` in a session of this client's own, committed the
moment the provider has been asked -- whether or not it answered -- so a crash
mid-run never un-counts a call the provider already served. A refused
reservation propagates as `QuotaExceeded`; the run turns that into a clean
stop rather than a failure.

The credentials travel in the query string, so no log line here may carry a
URL or the parameters. Only the country, the page, and the status are logged.
The transport is not so careful: httpx2 logs every request line, URL and
query included, at INFO. The process-wide redaction is what keeps the key out
of that line, and this client installs it and registers its key itself, so it
is protected however it was built.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx2
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.adzuna.source import (
    APP_ID,
    APP_KEY,
    DAILY_QUOTA,
    DEFAULT_BASE_URL,
    DEFAULT_COUNTRIES,
    SOURCE_KEY,
)
from job_ingestion.contracts import RawPage, RawRecord
from job_ingestion.errors import SourceResponseError
from job_ingestion.logging_support import install_secret_filter, register_secrets
from job_ingestion.transport import reserving_get

logger = logging.getLogger(__name__)

# The API serves at most 50 results to a page.
MAX_RESULTS_PER_PAGE = 50

# Adzuna keys its paths by lower-case ISO 3166-1 alpha-2 codes.
COUNTRY_CODE = re.compile(r"^[a-z]{2}$")

# What `Database.session` is: a callable opening one session for one call.
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True, slots=True)
class AdzunaConfig:
    """Bounded transport settings.

    The page budget is per country rather than per run so the walk spends
    the same on every market whatever order they are listed in. Together
    with the country list it fixes how many calls a run can make, which is
    what a schedule has to fit under the daily quota; `calls_per_run` is that
    number.
    """

    base_url: str = DEFAULT_BASE_URL
    countries: tuple[str, ...] = DEFAULT_COUNTRIES
    pages_per_country: int = 4
    results_per_page: int = MAX_RESULTS_PER_PAGE
    # Runs are hours apart, and sorting by date makes the newest results come
    # first: two days is enough to overlap the previous run without spending
    # pages on postings it already saw.
    max_days_old: int = 2
    timeout_seconds: float = 10.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if not self.countries:
            raise ValueError("countries must name at least one country")
        for country in self.countries:
            if not COUNTRY_CODE.match(country):
                raise ValueError(f"countries must be two-letter lower-case codes, not {country!r}")
        if self.pages_per_country < 1:
            raise ValueError("pages_per_country must be at least 1")
        if not 1 <= self.results_per_page <= MAX_RESULTS_PER_PAGE:
            raise ValueError(f"results_per_page must be between 1 and {MAX_RESULTS_PER_PAGE}")
        if self.max_days_old < 1:
            raise ValueError("max_days_old must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")

    @property
    def calls_per_run(self) -> int:
        """The most calls one complete walk can make."""
        return len(self.countries) * self.pages_per_country


def subject(country: str, page: int) -> str:
    """What one request is fetching, for error messages and logs."""
    return f"{country} page {page}"


def search_results(label: str, country: str, response: httpx2.Response) -> list[dict[str, Any]]:
    """Read the results out of one search response, each stamped with `country`.

    The stamp is the one thing this module adds to what the provider sent:
    `records` treats the country and the id together as the record's
    identity, because the id alone is not one across countries.
    """
    try:
        body = response.json()
    except ValueError as error:
        raise SourceResponseError(SOURCE_KEY, f"{label} is not valid JSON: {error}") from error
    if not isinstance(body, dict):
        raise SourceResponseError(SOURCE_KEY, f"{label} is not a JSON object")
    results = body.get("results")
    if not isinstance(results, list):
        raise SourceResponseError(SOURCE_KEY, f"{label} has no results array")
    stamped: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            raise SourceResponseError(SOURCE_KEY, f"{label} result {index} is not a JSON object")
        stamped.append({**result, "country": country})
    return stamped


class AdzunaClient:
    """Fetches untrusted search pages from Adzuna, one reserved call at a time."""

    def __init__(
        self,
        config: AdzunaConfig,
        credentials: Mapping[str, str],
        database_session_factory: SessionFactory,
        *,
        http_client: httpx2.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config
        # `require` already did both of these on the entry point's path, but a
        # client built anywhere else -- a command, a notebook, a test -- would
        # otherwise let httpx2 log the key in its request line. Both calls are
        # idempotent, so repeating them here costs nothing.
        install_secret_filter()
        register_secrets([credentials[APP_KEY.env]])
        # Held as query parameters from the start, so the only place the key
        # ever appears is the request that needs it.
        self._query = {
            "app_id": credentials[APP_ID.env],
            "app_key": credentials[APP_KEY.env],
            "results_per_page": str(config.results_per_page),
            "sort_by": "date",
            "max_days_old": str(config.max_days_old),
            "content-type": "application/json",
        }
        self._open_session = database_session_factory
        self._owns_http_client = http_client is None
        self._http_client = (
            http_client
            if http_client is not None
            else httpx2.AsyncClient(timeout=config.timeout_seconds)
        )
        self._sleeper = sleeper

    @property
    def source_key(self) -> str:
        return SOURCE_KEY

    async def fetch_page(self, country: str, page: int) -> tuple[RawRecord, ...]:
        """Reserve one call, make it, and return the page's stamped records.

        The session lives exactly as long as the call: opened for the
        reservation and committed however the call ends. Once the reservation
        is written the provider is asked, so whatever interrupts the request
        after that -- a transport failure, a cancellation, any error at all --
        finds a call that was served and must stay counted; the commit runs
        unconditionally rather than only on the failures this code can
        foresee. A refused reservation wrote nothing, so committing after
        `QuotaExceeded` is a no-op and it propagates as it is.
        """
        label = subject(country, page)
        async with self._open_session() as session:
            try:
                response = await reserving_get(
                    session,
                    SOURCE_KEY,
                    DAILY_QUOTA,
                    self._http_client,
                    f"{self.config.base_url}/{country}/search/{page}",
                    params=self._query,
                    timeout_seconds=self.config.timeout_seconds,
                    max_attempts=self.config.max_attempts,
                    retry_backoff_seconds=self.config.retry_backoff_seconds,
                    sleeper=self._sleeper,
                    subject=label,
                )
            finally:
                await session.commit()

        logger.info("%s returned status %d", label, response.status_code)
        if response.status_code != httpx2.codes.OK:
            raise SourceResponseError(
                SOURCE_KEY,
                f"{label} returned status {response.status_code}",
                status_code=response.status_code,
            )
        return tuple(search_results(label, country, response))

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        """Yield every country's pages in order, within the page budget.

        A short page is the end of that country's window and the walk moves
        to the next country. Nothing is recorded about whether every country
        came up short, because it would not mean the source was read to the
        end; see `reached_the_end`.
        """
        for country in self.config.countries:
            for page in range(1, self.config.pages_per_country + 1):
                records = await self.fetch_page(country, page)
                yield RawPage(records=records)
                if len(records) < self.config.results_per_page:
                    break

    @property
    def reached_the_end(self) -> bool:
        """Always False: a windowed walk cannot claim to have seen the source.

        `reached_the_end` licenses reconciliation to retire every posting a run
        did not see. Every page here is limited to `max_days_old`, so a run
        that ran every country short has still seen nothing older than the
        window, and claiming the end would retire every Adzuna posting older
        than a few days while it is still live there. Adzuna postings are
        therefore not retired by reconciliation yet; a rule for windowed
        sources is #376.
        """
        return False

    async def aclose(self) -> None:
        """Close the HTTP client if this client created it."""
        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
