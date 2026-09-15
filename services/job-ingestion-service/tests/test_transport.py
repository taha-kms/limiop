"""Retrying an HTTP GET the same way every ingestion client retries it."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx2
import pytest

from job_ingestion.errors import SourceUnavailableError
from job_ingestion.transport import retrying_get
from tests.boards.fakes import never_sleeps, responding

SOURCE_KEY = "fake"
SUBJECT = "the first page"


def rate_limited(retry_after: str | None = None) -> httpx2.Response:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return httpx2.Response(429, headers=headers)


def recording() -> tuple[Callable[[float], Awaitable[None]], list[float]]:
    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)

    return sleeper, slept


def get(
    *replies: httpx2.Response | Exception,
    max_attempts: int = 3,
    retry_backoff_seconds: float = 0.0,
    sleeper: Callable[[float], Awaitable[None]] = never_sleeps,
) -> httpx2.Response:
    """One call, so a raises block has a single thing that can throw."""

    async def run() -> httpx2.Response:
        http_client = responding(*replies)
        try:
            return await retrying_get(
                http_client,
                "https://example.test/api",
                params={"page": "1"},
                timeout_seconds=5.0,
                max_attempts=max_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                sleeper=sleeper,
                source_key=SOURCE_KEY,
                subject=SUBJECT,
            )
        finally:
            await http_client.aclose()

    return asyncio.run(run())


def test_a_successful_response_is_returned_on_the_first_attempt() -> None:
    response = get(httpx2.Response(200, json={"ok": True}))

    assert response.status_code == 200


def test_a_404_is_returned_not_raised() -> None:
    response = get(httpx2.Response(404))

    assert response.status_code == 404


def test_a_500_is_returned_not_raised() -> None:
    response = get(httpx2.Response(500))

    assert response.status_code == 500


def test_a_timeout_is_retried_and_then_succeeds() -> None:
    response = get(httpx2.TimeoutException("slow"), httpx2.Response(200))

    assert response.status_code == 200


def test_three_transport_errors_raise_source_unavailable() -> None:
    with pytest.raises(SourceUnavailableError, match="could not be reached"):
        get(*[httpx2.ConnectError("no route")] * 3)


def test_a_timeout_that_never_lifts_raises_with_its_own_wording() -> None:
    with pytest.raises(SourceUnavailableError, match="timed out"):
        get(*[httpx2.TimeoutException("slow")] * 3)


def test_a_rate_limit_that_lifts_is_retried_and_the_response_returned() -> None:
    sleeper, slept = recording()

    response = get(rate_limited("2"), httpx2.Response(200), sleeper=sleeper)

    assert response.status_code == 200
    assert slept == [2.0]


def test_a_rate_limit_that_never_lifts_raises() -> None:
    with pytest.raises(SourceUnavailableError, match="rate limited"):
        get(*[rate_limited()] * 3)


def test_a_malformed_retry_after_falls_back_to_the_configured_backoff() -> None:
    sleeper, slept = recording()

    get(
        rate_limited("whenever"),
        httpx2.Response(200),
        retry_backoff_seconds=0.25,
        sleeper=sleeper,
    )

    assert slept == [0.25]


def test_a_single_attempt_never_sleeps() -> None:
    sleeper, slept = recording()

    with pytest.raises(SourceUnavailableError):
        get(
            httpx2.TimeoutException("slow"),
            max_attempts=1,
            retry_backoff_seconds=5.0,
            sleeper=sleeper,
        )

    assert slept == []


def test_the_source_key_and_subject_are_carried_into_the_failure() -> None:
    with pytest.raises(SourceUnavailableError) as error:
        get(*[httpx2.ConnectError("no route")] * 3)

    assert error.value.source_key == SOURCE_KEY
    assert SUBJECT in error.value.message
