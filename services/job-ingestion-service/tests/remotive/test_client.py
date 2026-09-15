import asyncio
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx2
import pytest

from job_ingestion.errors import SourceResponseError, SourceUnavailableError
from job_ingestion.remotive.client import (
    DEFAULT_BASE_URL,
    SOURCE_KEY,
    USER_AGENT,
    RemotiveClient,
    RemotiveConfig,
)

FIXTURES = Path(__file__).parent / "fixtures"
FAST_CONFIG = RemotiveConfig(retry_backoff_seconds=0.0)


def job_record(job_id: int = 42) -> dict[str, object]:
    return {
        "id": job_id,
        "url": f"https://remotive.com/remote-jobs/data/remote-data-engineer-{job_id}",
        "title": "Remote Data Engineer",
        "company_name": "Acme Inc",
        "job_type": "full_time",
        "candidate_required_location": "Worldwide",
        "description": "<p>Build reliable pipelines.</p>",
        "publication_date": "2026-09-11T20:16:48",
    }


def jobs_body(records: list[dict[str, object]]) -> dict[str, object]:
    return {"job-count": len(records), "total-job-count": len(records), "jobs": records}


def client_for(
    handler: Callable[[httpx2.Request], httpx2.Response],
    config: RemotiveConfig = FAST_CONFIG,
) -> tuple[RemotiveClient, list[float]]:
    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)

    transport = httpx2.MockTransport(handler)
    http_client = httpx2.AsyncClient(transport=transport)
    return RemotiveClient(config, http_client=http_client, sleeper=sleeper), slept


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
    config = RemotiveConfig()

    assert config.base_url == DEFAULT_BASE_URL
    assert config.limit is None
    assert config.max_attempts >= 1
    assert config.timeout_seconds > 0


@pytest.mark.parametrize(
    ("field", "build"),
    [
        ("timeout_seconds", lambda: RemotiveConfig(timeout_seconds=0.0)),
        ("timeout_seconds", lambda: RemotiveConfig(timeout_seconds=-1.0)),
        ("limit", lambda: RemotiveConfig(limit=0)),
        ("limit", lambda: RemotiveConfig(limit=-1)),
        ("max_attempts", lambda: RemotiveConfig(max_attempts=0)),
        ("retry_backoff_seconds", lambda: RemotiveConfig(retry_backoff_seconds=-0.1)),
    ],
)
def test_config_rejects_unbounded_or_nonsense_limits(
    field: str,
    build: Callable[[], RemotiveConfig],
) -> None:
    with pytest.raises(ValueError, match=field):
        build()


def test_client_reports_its_source_key() -> None:
    client, _ = client_for(responding(json_response(jobs_body([]))))

    assert client.source_key == SOURCE_KEY


def test_fetch_page_returns_untrusted_records_unchanged() -> None:
    record = job_record()
    client, _ = client_for(responding(json_response(jobs_body([record]))))

    page = asyncio.run(client.fetch_page())

    assert page.records == (record,)
    assert page.has_next_page is False


def test_fetch_page_sends_no_limit_by_default() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        return json_response(jobs_body([]))

    client, _ = client_for(handler)

    asyncio.run(client.fetch_page())

    assert seen == [DEFAULT_BASE_URL]


def test_fetch_page_sends_the_configured_limit() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        return json_response(jobs_body([]))

    client, _ = client_for(handler, RemotiveConfig(limit=50, retry_backoff_seconds=0.0))

    asyncio.run(client.fetch_page())

    assert seen == [f"{DEFAULT_BASE_URL}?limit=50"]


def test_the_request_carries_the_skillsync_user_agent() -> None:
    seen: list[str | None] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers.get("user-agent"))
        return json_response(jobs_body([]))

    client, _ = client_for(handler)

    asyncio.run(client.fetch_page())

    assert seen == [USER_AGENT]


def test_fetch_pages_yields_the_one_page_and_reaches_the_end() -> None:
    client, _ = client_for(responding(json_response(jobs_body([job_record()]))))

    async def collect() -> list[dict[str, object]]:
        pages = [page async for page in client.fetch_pages()]
        return [record for page in pages for record in page.records]

    records = asyncio.run(collect())

    assert len(records) == 1
    assert client.reached_the_end is True


def test_reached_the_end_is_false_before_any_walk() -> None:
    client, _ = client_for(responding(json_response(jobs_body([]))))

    assert client.reached_the_end is False


def test_fetch_pages_does_not_report_reaching_the_end_on_failure() -> None:
    client, _ = client_for(
        responding(*[httpx2.TimeoutException("read timed out")] * FAST_CONFIG.max_attempts)
    )

    async def collect() -> None:
        async for _ in client.fetch_pages():
            pass

    with pytest.raises(SourceUnavailableError):
        asyncio.run(collect())

    assert client.reached_the_end is False


def test_timeout_becomes_a_transport_failure() -> None:
    client, _ = client_for(
        responding(*[httpx2.TimeoutException("read timed out")] * FAST_CONFIG.max_attempts)
    )

    with pytest.raises(SourceUnavailableError, match="timed out"):
        asyncio.run(client.fetch_page())


def test_connection_failure_becomes_a_transport_failure() -> None:
    client, _ = client_for(
        responding(*[httpx2.ConnectError("connection refused")] * FAST_CONFIG.max_attempts)
    )

    with pytest.raises(SourceUnavailableError, match="could not be reached"):
        asyncio.run(client.fetch_page())


def test_a_transport_failure_is_retried_within_the_attempt_budget() -> None:
    client, slept = client_for(
        responding(
            httpx2.TimeoutException("read timed out"),
            json_response(jobs_body([job_record()])),
        )
    )

    page = asyncio.run(client.fetch_page())

    assert len(page.records) == 1
    assert slept == [0.0]


def test_retrying_stops_at_the_attempt_budget() -> None:
    attempts = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        raise httpx2.TimeoutException("read timed out")

    client, slept = client_for(handler, RemotiveConfig(max_attempts=2, retry_backoff_seconds=0.0))

    with pytest.raises(SourceUnavailableError):
        asyncio.run(client.fetch_page())

    assert attempts == 2
    assert slept == [0.0]


def test_a_single_attempt_never_sleeps() -> None:
    client, slept = client_for(
        responding(httpx2.TimeoutException("read timed out")),
        RemotiveConfig(max_attempts=1, retry_backoff_seconds=5.0),
    )

    with pytest.raises(SourceUnavailableError):
        asyncio.run(client.fetch_page())

    assert slept == []


@pytest.mark.parametrize("status_code", [400, 404, 500, 503])
def test_non_success_status_is_not_retried_and_keeps_its_code(status_code: int) -> None:
    """429 is deliberately absent: a rate limit is a request to wait rather
    than an answer, the same rule every other client here follows."""
    attempts = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(status_code, text="nope")

    client, _ = client_for(handler)

    with pytest.raises(SourceResponseError) as error:
        asyncio.run(client.fetch_page())

    assert error.value.status_code == status_code
    assert attempts == 1


def test_a_body_that_is_not_json_is_rejected() -> None:
    client, _ = client_for(responding(httpx2.Response(200, text="<html>maintenance</html>")))

    with pytest.raises(SourceResponseError, match="not valid JSON"):
        asyncio.run(client.fetch_page())


def test_a_body_that_is_not_an_object_is_rejected() -> None:
    client, _ = client_for(responding(json_response([job_record()])))

    with pytest.raises(SourceResponseError, match="not a JSON object"):
        asyncio.run(client.fetch_page())


def test_a_body_without_a_jobs_array_is_rejected() -> None:
    client, _ = client_for(responding(json_response({"job-count": 0})))

    with pytest.raises(SourceResponseError, match="no jobs array"):
        asyncio.run(client.fetch_page())


def test_a_record_that_is_not_an_object_is_rejected() -> None:
    client, _ = client_for(responding(json_response({"jobs": [job_record(), "surprise"]})))

    with pytest.raises(SourceResponseError, match="record 1 is not a JSON object"):
        asyncio.run(client.fetch_page())


def test_an_injected_http_client_is_left_open() -> None:
    transport = httpx2.MockTransport(lambda request: json_response(jobs_body([])))
    http_client = httpx2.AsyncClient(transport=transport)

    async def exercise() -> bool:
        async with RemotiveClient(FAST_CONFIG, http_client=http_client):
            pass
        return http_client.is_closed

    assert asyncio.run(exercise()) is False
    asyncio.run(http_client.aclose())


def test_an_owned_http_client_is_closed() -> None:
    async def exercise() -> RemotiveClient:
        async with RemotiveClient(FAST_CONFIG) as client:
            return client

    client = asyncio.run(exercise())

    assert client._http_client.is_closed is True


def test_the_default_client_targets_the_public_api() -> None:
    async def exercise() -> str:
        async with RemotiveClient() as client:
            return client.config.base_url

    assert asyncio.run(exercise()) == DEFAULT_BASE_URL


def test_a_real_jobs_page_shape_is_accepted() -> None:
    body = json.loads((FIXTURES / "remote_jobs.json").read_text())
    client, _ = client_for(responding(json_response(body)))

    page = asyncio.run(client.fetch_page())

    assert page.records[0]["company_name"] == "Coalition Technologies "
    assert page.has_next_page is False
    assert len(page.records) == 3


def rate_limited(retry_after: str | None = None) -> httpx2.Response:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return httpx2.Response(429, headers=headers)


def test_a_rate_limit_that_lifts_is_retried_and_the_page_is_read() -> None:
    """The failure that would otherwise end a run where it stood."""
    client, slept = client_for(responding(rate_limited(), json_response(jobs_body([job_record()]))))

    page = asyncio.run(client.fetch_page())

    assert len(page.records) == 1
    assert slept == [FAST_CONFIG.retry_backoff_seconds]


def test_a_rate_limit_that_does_not_lift_still_fails_the_run() -> None:
    client, _ = client_for(responding(*[rate_limited()] * FAST_CONFIG.max_attempts))

    with pytest.raises(SourceUnavailableError, match="rate limited"):
        asyncio.run(client.fetch_page())


def test_retry_after_is_waited_rather_than_the_default_backoff() -> None:
    client, slept = client_for(
        responding(rate_limited("3"), json_response(jobs_body([job_record()])))
    )

    asyncio.run(client.fetch_page())

    assert slept == [3.0]


def test_a_malformed_retry_after_falls_back_to_the_configured_backoff() -> None:
    config = RemotiveConfig(retry_backoff_seconds=0.25)
    client, slept = client_for(
        responding(rate_limited("whenever"), json_response(jobs_body([job_record()]))), config
    )

    asyncio.run(client.fetch_page())

    assert slept == [0.25]


def test_a_status_that_is_not_a_rate_limit_is_still_not_retried() -> None:
    client, slept = client_for(responding(json_response({}, status_code=500)))

    with pytest.raises(SourceResponseError):
        asyncio.run(client.fetch_page())
    assert slept == []
