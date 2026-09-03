import asyncio

import httpx2

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.contracts import IngestionStage, RawPage
from tests.boards.fakes import hydrated_provider, never_sleeps, ok, routing


def listing(*identifiers: int) -> httpx2.Response:
    return ok(
        {
            "content": [
                {"id": identifier, "title": f"Job {identifier}"} for identifier in identifiers
            ]
        }
    )


def detail(identifier: int) -> httpx2.Response:
    return ok({"id": identifier, "description": f"Details of {identifier}"})


def client(routes: dict[str, httpx2.Response | Exception]) -> BoardClient:
    return BoardClient(
        hydrated_provider(),
        BoardConfig(boards=("acme",), retry_backoff_seconds=0.0),
        http_client=routing(routes),
        sleeper=never_sleeps,
    )


def collect(fetcher: BoardClient) -> list[RawPage]:
    async def run() -> list[RawPage]:
        return [page async for page in fetcher.fetch_pages()]

    return asyncio.run(run())


def test_each_record_is_merged_with_its_detail_in_listing_order() -> None:
    fetcher = client(
        {"/acme/jobs": listing(1, 2), "/postings/1": detail(1), "/postings/2": detail(2)}
    )

    pages = collect(fetcher)

    assert [record["id"] for record in pages[0].records] == [1, 2]
    assert pages[0].records[0]["description"] == "Details of 1"
    assert pages[0].records[0]["board"] == "acme"
    assert fetcher.reached_the_end is True


def test_a_record_whose_detail_cannot_be_read_is_dropped_and_denies_the_end() -> None:
    """A posting the run could not read looks exactly like one that is gone."""
    fetcher = client(
        {
            "/acme/jobs": listing(1, 2),
            "/postings/1": detail(1),
            "/postings/2": httpx2.Response(500),
        }
    )

    pages = collect(fetcher)

    assert [record["id"] for record in pages[0].records] == [1]
    assert len(fetcher.failures) == 1
    assert fetcher.failures[0].stage is IngestionStage.FETCH
    assert fetcher.failures[0].source_job_id == "acme:2"
    assert "returned status 500" in fetcher.failures[0].reason
    assert fetcher.reached_the_end is False


def test_an_unreachable_detail_is_retried_then_dropped() -> None:
    attempts: list[str] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        attempts.append(request.url.path)
        if request.url.path == "/acme/jobs":
            return listing(1)
        raise httpx2.ConnectError("down")

    fetcher = BoardClient(
        hydrated_provider(),
        BoardConfig(boards=("acme",), retry_backoff_seconds=0.0, max_attempts=2),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        sleeper=never_sleeps,
    )

    pages = collect(fetcher)

    assert pages[0].records == ()
    assert attempts.count("/postings/1") == 2
    assert "could not be reached" in fetcher.failures[0].reason


def test_a_detail_that_is_not_an_object_is_dropped() -> None:
    fetcher = client({"/acme/jobs": listing(1), "/postings/1": ok([1])})

    pages = collect(fetcher)

    assert pages[0].records == ()
    assert "is not a JSON object" in fetcher.failures[0].reason


def test_a_record_the_provider_has_no_detail_for_passes_through() -> None:
    fetcher = client({"/acme/jobs": ok({"content": [{"title": "No id"}]})})

    pages = collect(fetcher)

    assert pages[0].records == ({"title": "No id", "board": "acme"},)
    assert fetcher.reached_the_end is True


def test_details_are_fetched_at_most_concurrency_at_a_time() -> None:
    in_flight = 0
    peak = 0

    async def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal in_flight, peak
        if request.url.path == "/acme/jobs":
            return listing(1, 2, 3, 4, 5)
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return detail(int(request.url.path.rsplit("/", 1)[-1]))

    fetcher = BoardClient(
        hydrated_provider(),
        BoardConfig(boards=("acme",), detail_concurrency=2),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )

    pages = collect(fetcher)

    assert len(pages[0].records) == 5
    assert peak <= 2
