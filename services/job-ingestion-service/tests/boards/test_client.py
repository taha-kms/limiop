import asyncio
from typing import Any

import httpx2
import pytest

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.provider import BoardProvider
from job_ingestion.contracts import IngestionStage, RawPage
from job_ingestion.errors import SourceResponseError, SourceUnavailableError
from tests.boards.fakes import (
    FAKE_BASE_URL,
    jobs,
    json_provider,
    never_sleeps,
    ok,
    paginated_provider,
    responding,
    xml_provider,
)


def client(
    *replies: httpx2.Response | Exception,
    provider: BoardProvider[Any] | None = None,
    **overrides: Any,
) -> BoardClient:
    settings: dict[str, Any] = {"boards": ("acme",), "retry_backoff_seconds": 0.0}
    settings.update(overrides)
    return BoardClient(
        provider if provider is not None else json_provider(),
        BoardConfig(**settings),
        http_client=responding(*replies),
        sleeper=never_sleeps,
    )


def fetch(fetcher: BoardClient, slug: str = "acme") -> RawPage:
    return asyncio.run(fetcher.fetch_board(slug))


def collect(fetcher: BoardClient) -> list[RawPage]:
    async def run() -> list[RawPage]:
        return [page async for page in fetcher.fetch_pages()]

    return asyncio.run(run())


def test_the_client_is_named_by_its_provider() -> None:
    fetcher = client()

    assert fetcher.source_key == "fake"
    assert fetcher.base_url == FAKE_BASE_URL


def test_a_configured_base_url_wins_over_the_provider_default() -> None:
    assert client(base_url="https://eu.example.test").base_url == "https://eu.example.test"


def test_a_board_is_one_page_of_records_stamped_with_its_slug() -> None:
    pages = collect(client(ok(jobs(1, 2))))

    assert len(pages) == 1
    assert [record["id"] for record in pages[0].records] == [1, 2]
    assert {record["board"] for record in pages[0].records} == {"acme"}
    assert pages[0].next_page is None


def test_the_provider_names_the_request() -> None:
    seen: list[httpx2.URL] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url)
        return ok(jobs(1))

    fetcher = BoardClient(
        json_provider(),
        BoardConfig(boards=("acme",)),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )
    collect(fetcher)

    assert str(seen[0]) == f"{FAKE_BASE_URL}/acme/jobs"


def test_every_configured_board_is_read_and_the_end_is_reached() -> None:
    fetcher = client(ok(jobs(1)), ok(jobs(2)), boards=("acme", "globex"))

    pages = collect(fetcher)

    assert {record["board"] for page in pages for record in page.records} == {"acme", "globex"}
    assert fetcher.reached_the_end is True


def test_one_unreachable_board_does_not_discard_the_others() -> None:
    fetcher = client(
        httpx2.ConnectError("no route"),
        httpx2.ConnectError("no route"),
        httpx2.ConnectError("no route"),
        ok(jobs(1)),
        boards=("gone", "acme"),
    )

    pages = collect(fetcher)

    assert len(pages) == 1
    assert len(fetcher.failures) == 1
    assert fetcher.failures[0].stage is IngestionStage.FETCH
    assert "gone" in fetcher.failures[0].reason
    assert fetcher.reached_the_end is False


def test_a_non_success_status_is_reported_not_retried() -> None:
    fetcher = client(httpx2.Response(404), boards=("retired",))

    assert collect(fetcher) == []
    assert "returned status 404" in fetcher.failures[0].reason


def test_a_transport_failure_is_retried_before_giving_up() -> None:
    fetcher = client(httpx2.ConnectError("flaky"), ok(jobs(1)))

    assert len(collect(fetcher)) == 1
    assert fetcher.failures == []


def test_a_board_that_never_answers_raises_after_its_attempts() -> None:
    fetcher = client(*[httpx2.ConnectError("down")] * 3)

    with pytest.raises(SourceUnavailableError, match="could not be reached"):
        fetch(fetcher)


def test_a_timeout_is_reported_as_a_timeout() -> None:
    fetcher = client(*[httpx2.TimeoutException("slow")] * 3)

    with pytest.raises(SourceUnavailableError, match="timed out"):
        fetch(fetcher)


def test_an_unusable_body_is_the_providers_error() -> None:
    with pytest.raises(SourceResponseError, match="has no jobs array"):
        fetch(client(ok({"data": []})))


def test_a_rate_limited_board_is_retried_after_the_asked_wait() -> None:
    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)

    fetcher = BoardClient(
        json_provider(),
        BoardConfig(boards=("acme",), retry_backoff_seconds=0.25),
        http_client=responding(httpx2.Response(429, headers={"retry-after": "2"}), ok(jobs(1))),
        sleeper=sleeper,
    )

    assert fetch(fetcher).records
    assert slept == [2.0]


def test_a_board_that_stays_rate_limited_still_fails() -> None:
    fetcher = client(*[httpx2.Response(429)] * 3)

    with pytest.raises(SourceUnavailableError, match="rate limited"):
        fetch(fetcher)


def test_pages_are_walked_until_the_provider_says_there_are_no_more() -> None:
    seen: list[str] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.params["offset"])
        replies = {
            "0": {"jobs": [{"id": 1, "title": "One"}], "next": 1},
            "1": {"jobs": [{"id": 2, "title": "Two"}], "next": 2},
            "2": {"jobs": [{"id": 3, "title": "Three"}]},
        }
        return ok(replies[request.url.params["offset"]])

    fetcher = BoardClient(
        paginated_provider(),
        BoardConfig(boards=("acme",)),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )

    page = fetch(fetcher)

    assert [record["id"] for record in page.records] == [1, 2, 3]
    assert seen == ["0", "1", "2"]


def test_a_board_that_never_ends_is_refused_rather_than_walked_forever() -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        offset = int(request.url.params["offset"])
        return ok({"jobs": [{"id": offset, "title": "Again"}], "next": offset + 1})

    fetcher = BoardClient(
        paginated_provider(),
        BoardConfig(boards=("acme",), max_pages_per_board=3),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )

    with pytest.raises(SourceResponseError, match="did not end within 3 pages"):
        fetch(fetcher)


def test_an_xml_feed_reads_like_any_other_board() -> None:
    body = b"<feed><position><id>1</id><title>One</title></position></feed>"
    fetcher = client(httpx2.Response(200, content=body), provider=xml_provider())

    page = fetch(fetcher)

    assert page.records == ({"id": "1", "title": "One", "board": "acme"},)


def test_no_boards_configured_reads_nothing_and_reaches_the_end() -> None:
    fetcher = client(boards=())

    assert collect(fetcher) == []
    assert fetcher.reached_the_end is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("timeout_seconds", 0.0, id="timeout"),
        pytest.param("max_attempts", 0, id="attempts"),
        pytest.param("retry_backoff_seconds", -1.0, id="backoff"),
        pytest.param("max_pages_per_board", 0, id="pages"),
        pytest.param("detail_concurrency", 0, id="concurrency"),
        pytest.param("boards", ("  ",), id="blank board"),
    ],
)
def test_a_setting_without_a_bound_is_refused(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        BoardConfig(**{field: value})  # type: ignore[arg-type]


def test_the_client_closes_only_what_it_created() -> None:
    supplied = responding()

    async def run() -> None:
        async with BoardClient(json_provider(), http_client=supplied):
            pass

    asyncio.run(run())

    assert supplied.is_closed is False


def test_the_client_closes_what_it_created() -> None:
    async def run() -> httpx2.AsyncClient:
        fetcher = BoardClient(json_provider())
        async with fetcher:
            pass
        return fetcher._http_client

    assert asyncio.run(run()).is_closed is True
