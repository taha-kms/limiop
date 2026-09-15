import asyncio
from collections.abc import Callable

import httpx2
import pytest

from job_ingestion.contracts import RawPage, RawRecord
from job_ingestion.errors import SourceResponseError, SourceUnavailableError
from job_ingestion.himalayas.client import (
    DEFAULT_BASE_URL,
    SOURCE_KEY,
    HimalayasClient,
    HimalayasConfig,
)
from tests.boards.fakes import never_sleeps, ok, responding
from tests.himalayas.support import feed_page, page_body, posting

FAST_CONFIG = HimalayasConfig(retry_backoff_seconds=0.0)


def job_record(guid: str = "https://himalayas.app/jobs/a") -> dict[str, object]:
    return posting(guid=guid, applicationLink=guid)


def client(*replies: httpx2.Response | Exception, **overrides: object) -> HimalayasClient:
    settings: dict[str, object] = {"retry_backoff_seconds": 0.0}
    settings.update(overrides)
    return HimalayasClient(
        HimalayasConfig(**settings),  # type: ignore[arg-type]
        http_client=responding(*replies),
        sleeper=never_sleeps,
    )


def recording_client(
    *replies: httpx2.Response | Exception, **overrides: object
) -> tuple[HimalayasClient, list[float]]:
    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)

    settings: dict[str, object] = {"retry_backoff_seconds": 0.25}
    settings.update(overrides)
    return (
        HimalayasClient(
            HimalayasConfig(**settings),  # type: ignore[arg-type]
            http_client=responding(*replies),
            sleeper=sleeper,
        ),
        slept,
    )


def fetch(
    fetcher: HimalayasClient, cursor: str | None = None
) -> tuple[tuple[RawRecord, ...], str | None]:
    """One call, so a raises block has a single thing that can throw."""
    return asyncio.run(fetcher.fetch_page(cursor))


def collect(fetcher: HimalayasClient) -> list[RawPage]:
    """One call, so a raises block has a single thing that can throw."""

    async def run() -> list[RawPage]:
        return [page async for page in fetcher.fetch_pages()]

    return asyncio.run(run())


def test_config_defaults_bound_every_loop() -> None:
    config = HimalayasConfig()

    assert config.base_url == DEFAULT_BASE_URL
    assert config.limit == 20
    assert config.max_pages >= 1
    assert config.max_attempts >= 1
    assert config.timeout_seconds > 0


@pytest.mark.parametrize(
    ("field", "build"),
    [
        ("timeout_seconds", lambda: HimalayasConfig(timeout_seconds=0.0)),
        ("timeout_seconds", lambda: HimalayasConfig(timeout_seconds=-1.0)),
        ("max_pages", lambda: HimalayasConfig(max_pages=0)),
        ("max_attempts", lambda: HimalayasConfig(max_attempts=0)),
        ("retry_backoff_seconds", lambda: HimalayasConfig(retry_backoff_seconds=-0.1)),
        ("limit", lambda: HimalayasConfig(limit=0)),
        ("limit", lambda: HimalayasConfig(limit=21)),
    ],
)
def test_config_rejects_unbounded_or_nonsense_limits(
    field: str,
    build: Callable[[], HimalayasConfig],
) -> None:
    with pytest.raises(ValueError, match=field):
        build()


def test_client_reports_its_source_key() -> None:
    assert client().source_key == SOURCE_KEY


def test_fetch_page_returns_untrusted_records_unchanged() -> None:
    record = job_record()

    records, next_cursor = fetch(client(ok(feed_page([record]))))

    assert records == (record,)
    assert next_cursor is None


def test_fetch_page_requests_the_configured_limit_with_no_cursor_on_the_first_page() -> None:
    seen: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return ok(feed_page([]))

    fetcher = HimalayasClient(
        FAST_CONFIG, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    )

    fetch(fetcher)

    assert str(seen[0].url.copy_with(query=None)) == DEFAULT_BASE_URL
    assert dict(seen[0].url.params) == {"limit": "20"}


def test_fetch_page_carries_the_given_cursor() -> None:
    seen: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return ok(feed_page([]))

    fetcher = HimalayasClient(
        FAST_CONFIG, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    )

    fetch(fetcher, "some-cursor-value")

    assert dict(seen[0].url.params) == {"limit": "20", "cursor": "some-cursor-value"}


def test_fetch_page_honors_the_configured_limit() -> None:
    seen: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return ok(feed_page([]))

    fetcher = HimalayasClient(
        HimalayasConfig(limit=5, retry_backoff_seconds=0.0),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )

    fetch(fetcher)

    assert dict(seen[0].url.params)["limit"] == "5"


def test_fetch_page_reports_the_next_cursor() -> None:
    _, next_cursor = fetch(client(ok(feed_page([job_record()], next_cursor="page-two"))))

    assert next_cursor == "page-two"


def test_fetch_pages_walks_until_the_feed_ends() -> None:
    fetcher = client(
        ok(feed_page([job_record("https://himalayas.app/jobs/a")], next_cursor="cursor-1")),
        ok(feed_page([job_record("https://himalayas.app/jobs/b")], next_cursor=None)),
    )

    pages = collect(fetcher)

    assert [job["guid"] for page in pages for job in page.records] == [
        "https://himalayas.app/jobs/a",
        "https://himalayas.app/jobs/b",
    ]
    assert fetcher.reached_the_end is True


def test_fetch_pages_the_second_request_carries_the_first_pages_cursor() -> None:
    seen: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if len(seen) == 1:
            return ok(feed_page([job_record()], next_cursor="cursor-from-page-one"))
        return ok(feed_page([job_record()]))

    fetcher = HimalayasClient(
        FAST_CONFIG, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    )

    collect(fetcher)

    assert "cursor" not in dict(seen[0].url.params)
    assert dict(seen[1].url.params)["cursor"] == "cursor-from-page-one"


def test_fetch_pages_stops_at_the_page_limit() -> None:
    fetcher = client(ok(feed_page([job_record()], next_cursor="always-more")), max_pages=1)

    pages = collect(fetcher)

    assert len(pages) == 1
    assert fetcher.reached_the_end is False


def test_timeout_becomes_a_transport_failure() -> None:
    fetcher = client(*[httpx2.TimeoutException("read timed out")] * FAST_CONFIG.max_attempts)

    with pytest.raises(SourceUnavailableError, match="timed out"):
        fetch(fetcher)


def test_connection_failure_becomes_a_transport_failure() -> None:
    fetcher = client(*[httpx2.ConnectError("connection refused")] * FAST_CONFIG.max_attempts)

    with pytest.raises(SourceUnavailableError, match="could not be reached"):
        fetch(fetcher)


def test_a_transport_failure_is_retried_within_the_attempt_budget() -> None:
    fetcher, slept = recording_client(
        httpx2.TimeoutException("read timed out"),
        ok(feed_page([job_record()])),
        retry_backoff_seconds=0.0,
    )

    records, _ = fetch(fetcher)

    assert len(records) == 1
    assert slept == [0.0]


def test_retrying_stops_at_the_attempt_budget() -> None:
    attempts = 0

    def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        raise httpx2.TimeoutException("read timed out")

    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)

    fetcher = HimalayasClient(
        HimalayasConfig(max_attempts=2, retry_backoff_seconds=0.0),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        sleeper=sleeper,
    )

    with pytest.raises(SourceUnavailableError):
        fetch(fetcher)

    assert attempts == 2
    assert slept == [0.0]


def test_a_single_attempt_never_sleeps() -> None:
    fetcher, slept = recording_client(
        httpx2.TimeoutException("read timed out"), max_attempts=1, retry_backoff_seconds=5.0
    )

    with pytest.raises(SourceUnavailableError):
        fetch(fetcher)

    assert slept == []


@pytest.mark.parametrize("status_code", [400, 404, 500, 503])
def test_non_success_status_is_not_retried_and_keeps_its_code(status_code: int) -> None:
    attempts = 0

    def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(status_code, text="nope")

    fetcher = HimalayasClient(
        FAST_CONFIG, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    )

    with pytest.raises(SourceResponseError) as error:
        fetch(fetcher)

    assert error.value.status_code == status_code
    assert attempts == 1


def test_a_body_that_is_not_json_is_rejected() -> None:
    fetcher = client(httpx2.Response(200, text="<html>maintenance</html>"))

    with pytest.raises(SourceResponseError, match="not valid JSON"):
        fetch(fetcher)


def test_a_body_that_is_not_an_object_is_rejected() -> None:
    fetcher = client(ok([job_record()]))

    with pytest.raises(SourceResponseError, match="not a JSON object"):
        fetch(fetcher)


def test_a_body_without_a_jobs_array_is_rejected() -> None:
    fetcher = client(ok({"nextCursor": None}))

    with pytest.raises(SourceResponseError, match="no jobs array"):
        fetch(fetcher)


def test_a_record_that_is_not_an_object_is_rejected() -> None:
    fetcher = client(ok({"jobs": [job_record(), "surprise"]}))

    with pytest.raises(SourceResponseError, match="record 1 is not a JSON object"):
        fetch(fetcher)


def test_a_missing_next_cursor_ends_pagination() -> None:
    _, next_cursor = fetch(client(ok({"jobs": [job_record()]})))

    assert next_cursor is None


def test_an_unusable_next_cursor_ends_pagination() -> None:
    _, next_cursor = fetch(client(ok({"jobs": [], "nextCursor": 42})))

    assert next_cursor is None


def test_an_injected_http_client_is_left_open() -> None:
    http_client = responding(ok(feed_page([])))

    async def exercise() -> bool:
        async with HimalayasClient(FAST_CONFIG, http_client=http_client):
            pass
        return http_client.is_closed

    assert asyncio.run(exercise()) is False
    asyncio.run(http_client.aclose())


def test_an_owned_http_client_is_closed() -> None:
    async def exercise() -> HimalayasClient:
        async with HimalayasClient(FAST_CONFIG) as fetcher:
            return fetcher

    fetcher = asyncio.run(exercise())

    assert fetcher._http_client.is_closed is True


def test_the_default_client_targets_the_public_feed() -> None:
    async def exercise() -> str:
        async with HimalayasClient() as fetcher:
            return fetcher.config.base_url

    assert asyncio.run(exercise()) == DEFAULT_BASE_URL


def test_a_real_feed_page_shape_is_accepted() -> None:
    body = page_body("page_one.json")

    records, next_cursor = fetch(client(ok(body)))

    assert records[0]["companyName"] == "abridge"
    assert next_cursor == body["nextCursor"]


def rate_limited(retry_after: str | None = None) -> httpx2.Response:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return httpx2.Response(429, headers=headers)


def test_a_rate_limit_that_lifts_is_retried_and_the_page_is_read() -> None:
    fetcher, slept = recording_client(
        rate_limited(), ok(feed_page([job_record()])), retry_backoff_seconds=0.0
    )

    records, _ = fetch(fetcher)

    assert len(records) == 1
    assert slept == [0.0]


def test_a_rate_limit_that_does_not_lift_still_fails_the_run() -> None:
    fetcher = client(*[rate_limited()] * FAST_CONFIG.max_attempts)

    with pytest.raises(SourceUnavailableError, match="rate limited"):
        fetch(fetcher)


def test_retry_after_is_waited_rather_than_the_default_backoff() -> None:
    fetcher, slept = recording_client(rate_limited("3"), ok(feed_page([job_record()])))

    fetch(fetcher)

    assert slept == [3.0]


def test_a_malformed_retry_after_falls_back_to_the_configured_backoff() -> None:
    fetcher, slept = recording_client(
        rate_limited("whenever"), ok(feed_page([job_record()])), retry_backoff_seconds=0.25
    )

    fetch(fetcher)

    assert slept == [0.25]


def test_a_status_that_is_not_a_rate_limit_is_still_not_retried() -> None:
    fetcher, slept = recording_client(httpx2.Response(500, json={}))

    with pytest.raises(SourceResponseError):
        fetch(fetcher)
    assert slept == []


def test_a_rate_limit_part_way_through_pagination_is_retried_and_the_walk_continues() -> None:
    """The rate limit lifts within the attempt budget, so it costs a retry
    rather than the run: the same behavior `fetch_page` already covers, now
    exercised across a page boundary."""
    fetcher = client(
        ok(feed_page([job_record()], next_cursor="cursor-1")),
        rate_limited(),
        ok(feed_page([job_record()])),
    )

    assert len(collect(fetcher)) == 2
