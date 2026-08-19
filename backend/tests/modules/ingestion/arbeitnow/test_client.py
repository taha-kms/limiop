import asyncio
import json
from collections.abc import Callable, Iterator

import httpx2
import pytest

from app.modules.ingestion.arbeitnow.client import (
    DEFAULT_BASE_URL,
    SOURCE_KEY,
    ArbeitnowClient,
    ArbeitnowConfig,
)
from app.modules.ingestion.errors import SourceResponseError, SourceUnavailableError

FAST_CONFIG = ArbeitnowConfig(retry_backoff_seconds=0.0)


def job_record(slug: str = "external-42") -> dict[str, object]:
    return {
        "slug": slug,
        "company_name": "Acme GmbH",
        "title": "Data Engineer",
        "description": "<p>Build reliable data pipelines.</p>",
        "remote": True,
        "url": f"https://www.arbeitnow.com/jobs/{slug}",
        "tags": ["python"],
        "job_types": ["full_time"],
        "location": "Berlin",
        "created_at": 1755513600,
    }


def board_page(records: list[dict[str, object]], *, has_next: bool = False) -> dict[str, object]:
    return {
        "data": records,
        "links": {
            "next": "https://www.arbeitnow.com/api/job-board-api?page=2" if has_next else None
        },
        "meta": {"current_page": 1},
    }


def client_for(
    handler: Callable[[httpx2.Request], httpx2.Response],
    config: ArbeitnowConfig = FAST_CONFIG,
) -> tuple[ArbeitnowClient, list[float]]:
    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)

    transport = httpx2.MockTransport(handler)
    http_client = httpx2.AsyncClient(transport=transport)
    return ArbeitnowClient(config, http_client=http_client, sleeper=sleeper), slept


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
    config = ArbeitnowConfig()

    assert config.base_url == DEFAULT_BASE_URL
    assert config.max_pages >= 1
    assert config.max_attempts >= 1
    assert config.timeout_seconds > 0


@pytest.mark.parametrize(
    ("field", "build"),
    [
        ("timeout_seconds", lambda: ArbeitnowConfig(timeout_seconds=0.0)),
        ("timeout_seconds", lambda: ArbeitnowConfig(timeout_seconds=-1.0)),
        ("max_pages", lambda: ArbeitnowConfig(max_pages=0)),
        ("max_attempts", lambda: ArbeitnowConfig(max_attempts=0)),
        ("retry_backoff_seconds", lambda: ArbeitnowConfig(retry_backoff_seconds=-0.1)),
    ],
)
def test_config_rejects_unbounded_or_nonsense_limits(
    field: str,
    build: Callable[[], ArbeitnowConfig],
) -> None:
    with pytest.raises(ValueError, match=field):
        build()


def test_client_reports_its_source_key() -> None:
    client, _ = client_for(responding(json_response(board_page([]))))

    assert client.source_key == SOURCE_KEY


def test_fetch_page_returns_untrusted_records_unchanged() -> None:
    record = job_record()
    client, _ = client_for(responding(json_response(board_page([record]))))

    page = asyncio.run(client.fetch_page(1))

    assert page.records == (record,)
    assert page.has_next_page is False


def test_fetch_page_requests_the_configured_page() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        return json_response(board_page([]))

    client, _ = client_for(handler)

    asyncio.run(client.fetch_page(3))

    assert seen == [f"{DEFAULT_BASE_URL}?page=3"]


def test_fetch_page_reports_a_following_page() -> None:
    client, _ = client_for(responding(json_response(board_page([job_record()], has_next=True))))

    page = asyncio.run(client.fetch_page(1))

    assert page.has_next_page is True
    assert page.next_page == 2


def test_fetch_pages_walks_until_the_board_ends() -> None:
    client, _ = client_for(
        responding(
            json_response(board_page([job_record("a")], has_next=True)),
            json_response(board_page([job_record("b")], has_next=True)),
            json_response(board_page([job_record("c")])),
        )
    )

    async def collect() -> list[str]:
        slugs: list[str] = []
        async for page in client.fetch_pages():
            slugs.extend(str(record["slug"]) for record in page.records)
        return slugs

    assert asyncio.run(collect()) == ["a", "b", "c"]


def test_fetch_pages_stops_at_the_page_limit() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return json_response(board_page([job_record()], has_next=True))

    client, _ = client_for(handler, ArbeitnowConfig(max_pages=2, retry_backoff_seconds=0.0))

    async def count() -> int:
        pages = 0
        async for _ in client.fetch_pages():
            pages += 1
        return pages

    assert asyncio.run(count()) == 2


def test_timeout_becomes_a_transport_failure() -> None:
    client, _ = client_for(
        responding(*[httpx2.TimeoutException("read timed out")] * FAST_CONFIG.max_attempts)
    )

    with pytest.raises(SourceUnavailableError, match="timed out"):
        asyncio.run(client.fetch_page(1))


def test_connection_failure_becomes_a_transport_failure() -> None:
    client, _ = client_for(
        responding(*[httpx2.ConnectError("connection refused")] * FAST_CONFIG.max_attempts)
    )

    with pytest.raises(SourceUnavailableError, match="could not be reached"):
        asyncio.run(client.fetch_page(1))


def test_a_transport_failure_is_retried_within_the_attempt_budget() -> None:
    client, slept = client_for(
        responding(
            httpx2.TimeoutException("read timed out"),
            json_response(board_page([job_record()])),
        )
    )

    page = asyncio.run(client.fetch_page(1))

    assert len(page.records) == 1
    assert slept == [0.0]


def test_retrying_stops_at_the_attempt_budget() -> None:
    attempts = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        raise httpx2.TimeoutException("read timed out")

    client, slept = client_for(handler, ArbeitnowConfig(max_attempts=2, retry_backoff_seconds=0.0))

    with pytest.raises(SourceUnavailableError):
        asyncio.run(client.fetch_page(1))

    assert attempts == 2
    assert slept == [0.0]


def test_a_single_attempt_never_sleeps() -> None:
    client, slept = client_for(
        responding(httpx2.TimeoutException("read timed out")),
        ArbeitnowConfig(max_attempts=1, retry_backoff_seconds=5.0),
    )

    with pytest.raises(SourceUnavailableError):
        asyncio.run(client.fetch_page(1))

    assert slept == []


@pytest.mark.parametrize("status_code", [400, 404, 429, 500, 503])
def test_non_success_status_is_not_retried_and_keeps_its_code(status_code: int) -> None:
    attempts = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        return httpx2.Response(status_code, text="nope")

    client, _ = client_for(handler)

    with pytest.raises(SourceResponseError) as error:
        asyncio.run(client.fetch_page(1))

    assert error.value.status_code == status_code
    assert attempts == 1


def test_a_body_that_is_not_json_is_rejected() -> None:
    client, _ = client_for(responding(httpx2.Response(200, text="<html>maintenance</html>")))

    with pytest.raises(SourceResponseError, match="not valid JSON"):
        asyncio.run(client.fetch_page(1))


def test_a_body_that_is_not_an_object_is_rejected() -> None:
    client, _ = client_for(responding(json_response([job_record()])))

    with pytest.raises(SourceResponseError, match="not a JSON object"):
        asyncio.run(client.fetch_page(1))


def test_a_body_without_a_data_array_is_rejected() -> None:
    client, _ = client_for(responding(json_response({"meta": {"current_page": 1}})))

    with pytest.raises(SourceResponseError, match="no data array"):
        asyncio.run(client.fetch_page(1))


def test_a_record_that_is_not_an_object_is_rejected() -> None:
    client, _ = client_for(responding(json_response({"data": [job_record(), "surprise"]})))

    with pytest.raises(SourceResponseError, match="record 1 is not a JSON object"):
        asyncio.run(client.fetch_page(1))


def test_a_body_without_links_ends_pagination() -> None:
    client, _ = client_for(responding(json_response({"data": [job_record()]})))

    page = asyncio.run(client.fetch_page(1))

    assert page.next_page is None


def test_unusable_links_end_pagination() -> None:
    client, _ = client_for(responding(json_response({"data": [], "links": "gone"})))

    page = asyncio.run(client.fetch_page(1))

    assert page.next_page is None


def test_an_injected_http_client_is_left_open() -> None:
    transport = httpx2.MockTransport(lambda request: json_response(board_page([])))
    http_client = httpx2.AsyncClient(transport=transport)

    async def exercise() -> bool:
        async with ArbeitnowClient(FAST_CONFIG, http_client=http_client):
            pass
        return http_client.is_closed

    assert asyncio.run(exercise()) is False
    asyncio.run(http_client.aclose())


def test_an_owned_http_client_is_closed() -> None:
    async def exercise() -> ArbeitnowClient:
        async with ArbeitnowClient(FAST_CONFIG) as client:
            return client

    client = asyncio.run(exercise())

    assert client._http_client.is_closed is True


def test_the_default_client_targets_the_public_board() -> None:
    async def exercise() -> str:
        async with ArbeitnowClient() as client:
            return client.config.base_url

    assert asyncio.run(exercise()) == DEFAULT_BASE_URL


def test_a_real_board_page_shape_is_accepted() -> None:
    body = json.loads(json.dumps(board_page([job_record()], has_next=True)))
    client, _ = client_for(responding(json_response(body)))

    page = asyncio.run(client.fetch_page(1))

    assert page.records[0]["company_name"] == "Acme GmbH"
    assert page.next_page == 2
