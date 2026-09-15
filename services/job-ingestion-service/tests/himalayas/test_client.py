import asyncio
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx2
import pytest

from job_ingestion.errors import SourceResponseError, SourceUnavailableError
from job_ingestion.himalayas.client import (
    DEFAULT_BASE_URL,
    SOURCE_KEY,
    HimalayasClient,
    HimalayasConfig,
)

FIXTURES = Path(__file__).parent / "fixtures"
FAST_CONFIG = HimalayasConfig(retry_backoff_seconds=0.0)


def job_record(
    guid: str = "https://himalayas.app/companies/acme/jobs/data-engineer",
) -> dict[str, object]:
    return {
        "title": "Data Engineer",
        "companyName": "Acme",
        "description": "<p>Build reliable data pipelines.</p>",
        "applicationLink": guid,
        "employmentType": "Full Time",
        "locationRestrictions": ["United States"],
        "pubDate": 1755513600,
        "expiryDate": 1794649007,
        "guid": guid,
    }


def feed_page(
    records: list[dict[str, object]], *, next_cursor: str | None = None
) -> dict[str, object]:
    return {
        "comments": "cursor pagination",
        "updatedAt": 1755513600,
        "offset": 0,
        "limit": 20,
        "totalCount": len(records),
        "nextCursor": next_cursor,
        "jobs": records,
    }


def client_for(
    handler: Callable[[httpx2.Request], httpx2.Response],
    config: HimalayasConfig = FAST_CONFIG,
) -> tuple[HimalayasClient, list[float]]:
    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)

    transport = httpx2.MockTransport(handler)
    http_client = httpx2.AsyncClient(transport=transport)
    return HimalayasClient(config, http_client=http_client, sleeper=sleeper), slept


def responding(
    *responses: httpx2.Response | Exception,
) -> Callable[[httpx2.Request], httpx2.Response]:
    remaining: Iterator[httpx2.Response | Exception] = iter(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        outcome = next(remaining)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return handler


def json_response(body: object, status_code: int = 200) -> httpx2.Response:
    return httpx2.Response(status_code, json=body)


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
    client, _ = client_for(responding(json_response(feed_page([]))))

    assert client.source_key == SOURCE_KEY


def test_fetch_page_returns_untrusted_records_unchanged() -> None:
    record = job_record()
    client, _ = client_for(responding(json_response(feed_page([record]))))

    records, next_cursor = asyncio.run(client.fetch_page(None))

    assert records == (record,)
    assert next_cursor is None


def test_fetch_page_requests_the_configured_limit_with_no_cursor_on_the_first_page() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return json_response(feed_page([]))

    client, _ = client_for(handler)

    asyncio.run(client.fetch_page(None))

    assert str(seen[0].url.copy_with(query=None)) == DEFAULT_BASE_URL
    assert dict(seen[0].url.params) == {"limit": "20"}


def test_fetch_page_carries_the_given_cursor() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return json_response(feed_page([]))

    client, _ = client_for(handler)

    asyncio.run(client.fetch_page("some-cursor-value"))

    assert dict(seen[0].url.params) == {"limit": "20", "cursor": "some-cursor-value"}


def test_fetch_page_honors_the_configured_limit() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return json_response(feed_page([]))

    client, _ = client_for(handler, HimalayasConfig(limit=5, retry_backoff_seconds=0.0))

    asyncio.run(client.fetch_page(None))

    assert dict(seen[0].url.params)["limit"] == "5"


def test_fetch_page_reports_the_next_cursor() -> None:
    client, _ = client_for(
        responding(json_response(feed_page([job_record()], next_cursor="page-two")))
    )

    _, next_cursor = asyncio.run(client.fetch_page(None))

    assert next_cursor == "page-two"


def test_fetch_pages_walks_until_the_feed_ends() -> None:
    client, _ = client_for(
        responding(
            json_response(
                feed_page([job_record("https://himalayas.app/jobs/a")], next_cursor="cursor-1")
            ),
            json_response(
                feed_page([job_record("https://himalayas.app/jobs/b")], next_cursor=None)
            ),
        )
    )

    async def collect() -> list[str]:
        guids: list[str] = []
        async for page in client.fetch_pages():
            guids.extend(str(record["guid"]) for record in page.records)
        return guids

    assert asyncio.run(collect()) == [
        "https://himalayas.app/jobs/a",
        "https://himalayas.app/jobs/b",
    ]
    assert client.reached_the_end is True


def test_fetch_pages_the_second_request_carries_the_first_pages_cursor() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if len(seen) == 1:
            return json_response(feed_page([job_record()], next_cursor="cursor-from-page-one"))
        return json_response(feed_page([job_record()]))

    client, _ = client_for(handler)

    async def collect() -> None:
        async for _ in client.fetch_pages():
            pass

    asyncio.run(collect())

    assert "cursor" not in dict(seen[0].url.params)
    assert dict(seen[1].url.params)["cursor"] == "cursor-from-page-one"


def test_fetch_pages_stops_at_the_page_limit() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return json_response(feed_page([job_record()], next_cursor="always-more"))

    client, _ = client_for(handler, HimalayasConfig(max_pages=1, retry_backoff_seconds=0.0))

    async def count() -> int:
        pages = 0
        async for _ in client.fetch_pages():
            pages += 1
        return pages

    assert asyncio.run(count()) == 1
    assert client.reached_the_end is False


def test_timeout_becomes_a_transport_failure() -> None:
    client, _ = client_for(
        responding(*[httpx2.TimeoutException("read timed out")] * FAST_CONFIG.max_attempts)
    )

    with pytest.raises(SourceUnavailableError, match="timed out"):
        asyncio.run(client.fetch_page(None))


def test_connection_failure_becomes_a_transport_failure() -> None:
    client, _ = client_for(
        responding(*[httpx2.ConnectError("connection refused")] * FAST_CONFIG.max_attempts)
    )

    with pytest.raises(SourceUnavailableError, match="could not be reached"):
        asyncio.run(client.fetch_page(None))


def test_a_transport_failure_is_retried_within_the_attempt_budget() -> None:
    client, slept = client_for(
        responding(
            httpx2.TimeoutException("read timed out"),
            json_response(feed_page([job_record()])),
        )
    )

    records, _ = asyncio.run(client.fetch_page(None))

    assert len(records) == 1
    assert slept == [0.0]


def test_retrying_stops_at_the_attempt_budget() -> None:
    attempts = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        raise httpx2.TimeoutException("read timed out")

    client, slept = client_for(handler, HimalayasConfig(max_attempts=2, retry_backoff_seconds=0.0))

    with pytest.raises(SourceUnavailableError):
        asyncio.run(client.fetch_page(None))

    assert attempts == 2
    assert slept == [0.0]


def test_a_single_attempt_never_sleeps() -> None:
    client, slept = client_for(
        responding(httpx2.TimeoutException("read timed out")),
        HimalayasConfig(max_attempts=1, retry_backoff_seconds=5.0),
    )

    with pytest.raises(SourceUnavailableError):
        asyncio.run(client.fetch_page(None))

    assert slept == []


@pytest.mark.parametrize("status_code", [400, 404, 500, 503])
def test_non_success_status_is_not_retried_and_keeps_its_code(status_code: int) -> None:
    attempts = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(status_code, text="nope")

    client, _ = client_for(handler)

    with pytest.raises(SourceResponseError) as error:
        asyncio.run(client.fetch_page(None))

    assert error.value.status_code == status_code
    assert attempts == 1


def test_a_body_that_is_not_json_is_rejected() -> None:
    client, _ = client_for(responding(httpx2.Response(200, text="<html>maintenance</html>")))

    with pytest.raises(SourceResponseError, match="not valid JSON"):
        asyncio.run(client.fetch_page(None))


def test_a_body_that_is_not_an_object_is_rejected() -> None:
    client, _ = client_for(responding(json_response([job_record()])))

    with pytest.raises(SourceResponseError, match="not a JSON object"):
        asyncio.run(client.fetch_page(None))


def test_a_body_without_a_jobs_array_is_rejected() -> None:
    client, _ = client_for(responding(json_response({"nextCursor": None})))

    with pytest.raises(SourceResponseError, match="no jobs array"):
        asyncio.run(client.fetch_page(None))


def test_a_record_that_is_not_an_object_is_rejected() -> None:
    client, _ = client_for(responding(json_response({"jobs": [job_record(), "surprise"]})))

    with pytest.raises(SourceResponseError, match="record 1 is not a JSON object"):
        asyncio.run(client.fetch_page(None))


def test_a_missing_next_cursor_ends_pagination() -> None:
    client, _ = client_for(responding(json_response({"jobs": [job_record()]})))

    _, next_cursor = asyncio.run(client.fetch_page(None))

    assert next_cursor is None


def test_an_unusable_next_cursor_ends_pagination() -> None:
    client, _ = client_for(responding(json_response({"jobs": [], "nextCursor": 42})))

    _, next_cursor = asyncio.run(client.fetch_page(None))

    assert next_cursor is None


def test_an_injected_http_client_is_left_open() -> None:
    transport = httpx2.MockTransport(lambda request: json_response(feed_page([])))
    http_client = httpx2.AsyncClient(transport=transport)

    async def exercise() -> bool:
        async with HimalayasClient(FAST_CONFIG, http_client=http_client):
            pass
        return http_client.is_closed

    assert asyncio.run(exercise()) is False
    asyncio.run(http_client.aclose())


def test_an_owned_http_client_is_closed() -> None:
    async def exercise() -> HimalayasClient:
        async with HimalayasClient(FAST_CONFIG) as client:
            return client

    client = asyncio.run(exercise())

    assert client._http_client.is_closed is True


def test_the_default_client_targets_the_public_feed() -> None:
    async def exercise() -> str:
        async with HimalayasClient() as client:
            return client.config.base_url

    assert asyncio.run(exercise()) == DEFAULT_BASE_URL


def test_a_real_feed_page_shape_is_accepted() -> None:
    body = json.loads((FIXTURES / "page_one.json").read_text())
    client, _ = client_for(responding(json_response(body)))

    records, next_cursor = asyncio.run(client.fetch_page(None))

    assert records[0]["companyName"] == "abridge"
    assert next_cursor == body["nextCursor"]


def rate_limited(retry_after: str | None = None) -> httpx2.Response:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return httpx2.Response(429, headers=headers)


def test_a_rate_limit_that_lifts_is_retried_and_the_page_is_read() -> None:
    client, slept = client_for(responding(rate_limited(), json_response(feed_page([job_record()]))))

    records, _ = asyncio.run(client.fetch_page(None))

    assert len(records) == 1
    assert slept == [FAST_CONFIG.retry_backoff_seconds]


def test_a_rate_limit_that_does_not_lift_still_fails_the_run() -> None:
    client, _ = client_for(responding(*[rate_limited()] * FAST_CONFIG.max_attempts))

    with pytest.raises(SourceUnavailableError, match="rate limited"):
        asyncio.run(client.fetch_page(None))


def test_retry_after_is_waited_rather_than_the_default_backoff() -> None:
    client, slept = client_for(
        responding(rate_limited("3"), json_response(feed_page([job_record()])))
    )

    asyncio.run(client.fetch_page(None))

    assert slept == [3.0]


def test_a_malformed_retry_after_falls_back_to_the_configured_backoff() -> None:
    config = HimalayasConfig(retry_backoff_seconds=0.25)
    client, slept = client_for(
        responding(rate_limited("whenever"), json_response(feed_page([job_record()]))), config
    )

    asyncio.run(client.fetch_page(None))

    assert slept == [0.25]


def test_a_status_that_is_not_a_rate_limit_is_still_not_retried() -> None:
    client, slept = client_for(responding(json_response({}, status_code=500)))

    with pytest.raises(SourceResponseError):
        asyncio.run(client.fetch_page(None))
    assert slept == []


def test_a_rate_limit_part_way_through_pagination_is_retried_and_the_walk_continues() -> None:
    """The rate limit lifts within the attempt budget, so it costs a retry
    rather than the run: the same behavior `fetch_page` already covers, now
    exercised across a page boundary."""

    async def collect() -> int:
        client, _ = client_for(
            responding(
                json_response(feed_page([job_record()], next_cursor="cursor-1")),
                rate_limited(),
                json_response(feed_page([job_record()])),
            )
        )
        return len([page async for page in client.fetch_pages()])

    assert asyncio.run(collect()) == 2
