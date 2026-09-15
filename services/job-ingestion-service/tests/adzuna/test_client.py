import asyncio
from collections.abc import Callable

import httpx2
import pytest
from pydantic import PostgresDsn

from job_ingestion.adzuna.client import (
    MAX_RESULTS_PER_PAGE,
    AdzunaClient,
    AdzunaConfig,
    search_results,
)
from job_ingestion.adzuna.source import (
    DAILY_QUOTA,
    DEFAULT_BASE_URL,
    DEFAULT_COUNTRIES,
    SOURCE_KEY,
)
from job_ingestion.contracts import RawPage
from job_ingestion.database import Database
from job_ingestion.errors import QuotaExceeded, SourceResponseError, SourceUnavailableError
from job_ingestion.quota import Quota, reserve, used_today
from tests.adzuna.support import (
    APP_ID,
    APP_KEY,
    CREDENTIALS,
    never_opened,
    page_body,
    recording,
    run_database_test,
    search_page,
)
from tests.boards.fakes import never_sleeps, ok
from tests.support.logs import capturing_logs

# Two countries, two pages each, three results to a full page: the fixture
# pages are then exactly full, so a walk continues past them until the page
# budget, and a page with fewer results is short.
WALK = {"countries": ("gb", "de"), "pages_per_country": 2, "results_per_page": 3}


def full_page(country: str) -> httpx2.Response:
    return ok(page_body(country))


def short_page(country: str, results: int = 2) -> httpx2.Response:
    return ok(search_page(page_body(country)["results"][:results]))


def client(
    database: Database, *replies: httpx2.Response | Exception, **overrides: object
) -> tuple[AdzunaClient, list[httpx2.Request]]:
    settings: dict[str, object] = {"retry_backoff_seconds": 0.0, **WALK}
    settings.update(overrides)
    http_client, requests = recording(*replies)
    fetcher = AdzunaClient(
        AdzunaConfig(**settings),  # type: ignore[arg-type]
        CREDENTIALS,
        database.session,
        http_client=http_client,
        sleeper=never_sleeps,
    )
    return fetcher, requests


async def collect(fetcher: AdzunaClient) -> list[RawPage]:
    return [page async for page in fetcher.fetch_pages()]


async def spent(database: Database) -> int:
    async with database.session() as session:
        return await used_today(session, SOURCE_KEY)


async def spend(database: Database, calls: int) -> None:
    async with database.session() as session:
        assert await reserve(session, SOURCE_KEY, calls=calls, quota=Quota(per_day=calls))
        await session.commit()


def test_config_defaults_bound_every_loop() -> None:
    config = AdzunaConfig()

    assert config.base_url == DEFAULT_BASE_URL
    assert config.countries == DEFAULT_COUNTRIES
    assert config.results_per_page == MAX_RESULTS_PER_PAGE
    assert config.pages_per_country == 4
    assert config.max_days_old == 2
    assert config.max_attempts >= 1
    assert config.timeout_seconds > 0
    assert config.calls_per_run == len(DEFAULT_COUNTRIES) * 4


@pytest.mark.parametrize(
    ("field", "build"),
    [
        ("countries", lambda: AdzunaConfig(countries=())),
        ("countries", lambda: AdzunaConfig(countries=("GB",))),
        ("countries", lambda: AdzunaConfig(countries=("gb", "deu"))),
        ("pages_per_country", lambda: AdzunaConfig(pages_per_country=0)),
        ("results_per_page", lambda: AdzunaConfig(results_per_page=0)),
        ("results_per_page", lambda: AdzunaConfig(results_per_page=51)),
        ("max_days_old", lambda: AdzunaConfig(max_days_old=0)),
        ("timeout_seconds", lambda: AdzunaConfig(timeout_seconds=0.0)),
        ("max_attempts", lambda: AdzunaConfig(max_attempts=0)),
        ("retry_backoff_seconds", lambda: AdzunaConfig(retry_backoff_seconds=-0.1)),
    ],
)
def test_config_rejects_unbounded_or_nonsense_limits(
    field: str, build: Callable[[], AdzunaConfig]
) -> None:
    with pytest.raises(ValueError, match=field):
        build()


def test_the_client_reports_its_source_key() -> None:
    fetcher = AdzunaClient(AdzunaConfig(), CREDENTIALS, never_opened)  # type: ignore[arg-type]

    assert fetcher.source_key == SOURCE_KEY
    assert fetcher.reached_the_end is False


@pytest.mark.integration
def test_the_walk_covers_every_country_and_page_and_reserves_each_call(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        fetcher, requests = client(
            database, full_page("gb"), full_page("gb"), full_page("de"), full_page("de")
        )

        pages = await collect(fetcher)

        assert [record["country"] for page in pages for record in page.records] == (
            ["gb"] * 6 + ["de"] * 6
        )
        assert [request.url.path for request in requests] == [
            "/v1/api/jobs/gb/search/1",
            "/v1/api/jobs/gb/search/2",
            "/v1/api/jobs/de/search/1",
            "/v1/api/jobs/de/search/2",
        ]
        assert await spent(database) == 4
        # Every country still had a full page when its budget ran out, so
        # nothing here says the source was read to the end.
        assert fetcher.reached_the_end is False

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_short_page_ends_that_country_and_the_walk_moves_on(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        fetcher, requests = client(database, short_page("gb"), full_page("de"), full_page("de"))

        pages = await collect(fetcher)

        assert [len(page.records) for page in pages] == [2, 3, 3]
        assert [request.url.path for request in requests] == [
            "/v1/api/jobs/gb/search/1",
            "/v1/api/jobs/de/search/1",
            "/v1/api/jobs/de/search/2",
        ]
        assert await spent(database) == 3
        assert fetcher.reached_the_end is False

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_end_is_reached_only_when_every_country_runs_out(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        fetcher, _ = client(database, short_page("gb"), short_page("de", results=0))

        pages = await collect(fetcher)

        assert [len(page.records) for page in pages] == [2, 0]
        assert fetcher.reached_the_end is True

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_quota_refusal_propagates_after_the_pages_already_yielded(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await spend(database, DAILY_QUOTA.per_day - 2)
        fetcher, requests = client(database, full_page("gb"), full_page("gb"), full_page("de"))
        pages: list[RawPage] = []

        with pytest.raises(QuotaExceeded) as error:
            async for page in fetcher.fetch_pages():
                pages.append(page)

        assert len(pages) == 2
        assert len(requests) == 2
        assert error.value.per_day == DAILY_QUOTA.per_day
        assert await spent(database) == DAILY_QUOTA.per_day
        assert fetcher.reached_the_end is False

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_spent_budget_makes_no_request_at_all(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await spend(database, DAILY_QUOTA.per_day)
        fetcher, requests = client(database, full_page("gb"))

        with pytest.raises(QuotaExceeded):
            await collect(fetcher)

        assert requests == []

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_credentials_travel_in_the_query_and_never_in_a_log_record(
    database_url: PostgresDsn,
) -> None:
    """Nothing here relies on the redaction filter: the key is not registered
    for it, so what this proves is that the client itself never logs a URL
    or its parameters, only the country, the page, and the status."""

    async def exercise(database: Database) -> None:
        fetcher, requests = client(database, short_page("gb"), short_page("de"))

        with capturing_logs("job_ingestion") as messages:
            await collect(fetcher)

        assert dict(requests[0].url.params) == {
            "app_id": APP_ID,
            "app_key": APP_KEY,
            "results_per_page": "3",
            "sort_by": "date",
            "max_days_old": "2",
            "content-type": "application/json",
        }
        assert "authorization" not in requests[0].headers
        assert any("gb page 1" in message and "200" in message for message in messages)
        logged = "\n".join(messages)
        assert APP_KEY not in logged
        assert APP_ID not in logged
        assert "app_key" not in logged
        assert "/search/" not in logged

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_provider_that_never_answers_still_spends_the_call(database_url: PostgresDsn) -> None:
    """The reservation is what the provider was asked under, and it was asked
    up to the attempt budget; rolling the reservation back with the failure
    would let the next run under-count what the provider already served."""

    async def exercise(database: Database) -> None:
        fetcher, requests = client(
            database, *[httpx2.TimeoutException("read timed out")] * 3, max_attempts=3
        )

        with pytest.raises(SourceUnavailableError, match="gb page 1 timed out"):
            await collect(fetcher)

        assert len(requests) == 3
        assert await spent(database) == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_rate_limit_that_lifts_costs_one_reservation(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        fetcher, requests = client(
            database,
            httpx2.Response(429, headers={"retry-after": "0"}),
            short_page("gb"),
            short_page("de"),
        )

        pages = await collect(fetcher)

        assert len(pages) == 2
        assert len(requests) == 3
        assert await spent(database) == 2

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unusable_answer_is_reported_with_its_status(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        fetcher, _ = client(database, httpx2.Response(503, text="down"))

        with pytest.raises(SourceResponseError, match="gb page 1 returned status 503") as error:
            await collect(fetcher)

        assert error.value.status_code == 503
        assert await spent(database) == 1

    run_database_test(database_url, exercise)


def test_search_results_are_stamped_with_their_country() -> None:
    results = search_results("de page 1", "de", ok(page_body("de")))

    assert len(results) == 3
    assert {result["country"] for result in results} == {"de"}
    assert results[0]["id"] == "5311980427"


@pytest.mark.parametrize(
    ("response", "problem"),
    [
        (httpx2.Response(200, text="<html>maintenance</html>"), "is not valid JSON"),
        (ok([{"id": "1"}]), "is not a JSON object"),
        (ok({"count": 0}), "has no results array"),
        (ok({"results": {"id": "1"}}), "has no results array"),
        (ok({"results": [{"id": "1"}, "surprise"]}), "result 1 is not a JSON object"),
    ],
)
def test_a_malformed_search_response_is_rejected(response: httpx2.Response, problem: str) -> None:
    with pytest.raises(SourceResponseError, match=f"gb page 1 {problem}"):
        search_results("gb page 1", "gb", response)


def test_an_injected_http_client_is_left_open() -> None:
    http_client, _ = recording()

    async def exercise() -> bool:
        async with AdzunaClient(
            AdzunaConfig(),
            CREDENTIALS,
            never_opened,  # type: ignore[arg-type]
            http_client=http_client,
        ):
            pass
        return http_client.is_closed

    assert asyncio.run(exercise()) is False
    asyncio.run(http_client.aclose())


def test_an_owned_http_client_is_closed() -> None:
    async def exercise() -> AdzunaClient:
        async with AdzunaClient(AdzunaConfig(), CREDENTIALS, never_opened) as fetcher:  # type: ignore[arg-type]
            return fetcher

    assert asyncio.run(exercise())._http_client.is_closed is True
