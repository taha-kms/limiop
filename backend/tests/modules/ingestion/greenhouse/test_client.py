import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest

from app.modules.ingestion.contracts import IngestionStage, RawPage
from app.modules.ingestion.errors import SourceResponseError, SourceUnavailableError
from app.modules.ingestion.greenhouse.client import GreenhouseClient, GreenhouseConfig

FIXTURE = Path(__file__).parent / "fixtures" / "board.json"


def board_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(FIXTURE.read_text())
    return body


async def never_sleeps(_seconds: float) -> None:
    return None


def responding(*replies: httpx2.Response | Exception) -> httpx2.AsyncClient:
    """A client answering each request with the next reply, in order."""
    remaining: Iterator[httpx2.Response | Exception] = iter(replies)

    def handle(request: httpx2.Request) -> httpx2.Response:
        reply = next(remaining)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


def client(*replies: httpx2.Response | Exception, **overrides: Any) -> GreenhouseClient:
    settings = {"boards": ("hudl",), "retry_backoff_seconds": 0.0}
    settings.update(overrides)
    return GreenhouseClient(
        GreenhouseConfig(**settings),  # type: ignore[arg-type]
        http_client=responding(*replies),
        sleeper=never_sleeps,
    )


def ok(body: Any) -> httpx2.Response:
    return httpx2.Response(200, json=body)


def collect(fetcher: GreenhouseClient) -> list[RawPage]:
    async def run() -> list[RawPage]:
        return [page async for page in fetcher.fetch_pages()]

    return asyncio.run(run())


def test_a_board_is_one_page_of_records() -> None:
    pages = collect(client(ok(board_body())))

    assert len(pages) == 1
    assert len(pages[0].records) == 2
    assert pages[0].next_page is None


def test_each_record_carries_the_board_it_came_from() -> None:
    """A posting identifier is only unique within its own board."""
    pages = collect(client(ok(board_body())))

    assert {record["board"] for record in pages[0].records} == {"hudl"}


def test_every_configured_board_is_read() -> None:
    fetcher = client(ok(board_body()), ok(board_body()), boards=("hudl", "anthropic"))

    pages = collect(fetcher)

    assert len(pages) == 2
    assert {record["board"] for page in pages for record in page.records} == {"hudl", "anthropic"}


def test_the_description_is_asked_for() -> None:
    """A posting without one cannot be normalized, and it is not sent by default."""
    seen: list[httpx2.URL] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url)
        return ok(board_body())

    fetcher = GreenhouseClient(
        GreenhouseConfig(boards=("hudl",)),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )
    collect(fetcher)

    assert seen[0].params["content"] == "true"
    assert seen[0].path.endswith("/hudl/jobs")


def test_one_unreachable_board_does_not_discard_the_others() -> None:
    """Boards are separate companies. One going away says nothing about the rest."""
    fetcher = client(
        httpx2.ConnectError("no route"),
        httpx2.ConnectError("no route"),
        httpx2.ConnectError("no route"),
        ok(board_body()),
        boards=("gone", "hudl"),
    )

    pages = collect(fetcher)

    assert len(pages) == 1
    assert {record["board"] for record in pages[0].records} == {"hudl"}
    assert len(fetcher.failures) == 1
    assert fetcher.failures[0].stage is IngestionStage.FETCH
    assert "gone" in fetcher.failures[0].reason


def test_a_board_that_no_longer_exists_is_reported_not_retried() -> None:
    """A 404 is an answer. Retrying it just asks the same question again."""
    fetcher = client(httpx2.Response(404), boards=("retired",))

    pages = collect(fetcher)

    assert pages == []
    assert len(fetcher.failures) == 1
    assert "404" in fetcher.failures[0].reason


def test_a_transport_failure_is_retried_before_giving_up() -> None:
    fetcher = client(httpx2.ConnectError("flaky"), ok(board_body()))

    pages = collect(fetcher)

    assert len(pages) == 1
    assert fetcher.failures == []


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        pytest.param(httpx2.Response(200, text="not json"), "not valid JSON", id="not json"),
        pytest.param(ok([1, 2]), "not a JSON object", id="not an object"),
        pytest.param(ok({"data": []}), "no jobs array", id="no jobs array"),
        pytest.param(ok({"jobs": ["nope"]}), "not a JSON object", id="record not an object"),
    ],
)
def test_an_unusable_body_is_a_source_response_error(reply: httpx2.Response, expected: str) -> None:
    fetcher = client(reply)

    with pytest.raises(SourceResponseError, match=expected):
        asyncio.run(fetcher.fetch_board("hudl"))


def test_a_board_that_never_answers_raises_after_its_attempts() -> None:
    fetcher = client(
        httpx2.ConnectError("down"),
        httpx2.ConnectError("down"),
        httpx2.ConnectError("down"),
    )

    with pytest.raises(SourceUnavailableError, match="could not be reached"):
        asyncio.run(fetcher.fetch_board("hudl"))


def test_a_timeout_is_reported_as_a_timeout() -> None:
    fetcher = client(*[httpx2.TimeoutException("slow")] * 3)

    with pytest.raises(SourceUnavailableError, match="timed out"):
        asyncio.run(fetcher.fetch_board("hudl"))


def test_no_boards_configured_reads_nothing() -> None:
    assert collect(client(boards=())) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("timeout_seconds", 0.0, id="timeout"),
        pytest.param("max_attempts", 0, id="attempts"),
        pytest.param("retry_backoff_seconds", -1.0, id="backoff"),
        pytest.param("boards", ("  ",), id="blank board"),
    ],
)
def test_a_setting_without_a_bound_is_refused(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        GreenhouseConfig(**{field: value})  # type: ignore[arg-type]


def test_the_client_closes_only_what_it_created() -> None:
    supplied = responding()

    async def run() -> None:
        async with GreenhouseClient(GreenhouseConfig(), http_client=supplied):
            pass

    asyncio.run(run())

    assert supplied.is_closed is False


def test_the_client_names_its_source() -> None:
    assert client().source_key == "greenhouse"


def test_the_client_closes_what_it_created() -> None:
    async def run() -> httpx2.AsyncClient:
        fetcher = GreenhouseClient(GreenhouseConfig())
        async with fetcher:
            pass
        return fetcher._http_client

    assert asyncio.run(run()).is_closed is True
