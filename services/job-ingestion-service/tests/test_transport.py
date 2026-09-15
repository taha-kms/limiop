"""Retrying an HTTP GET the same way every ingestion client retries it."""

import asyncio
from collections.abc import Awaitable, Callable, Iterator

import httpx2
import pytest
from platform_db.models import SourceQuotaUsage
from pydantic import PostgresDsn
from sqlalchemy import delete

from job_ingestion import logging_support
from job_ingestion.database import Database
from job_ingestion.errors import QuotaExceeded, SourceUnavailableError
from job_ingestion.logging_support import install_secret_filter, register_secrets
from job_ingestion.quota import Quota, reserve, used_today
from job_ingestion.transport import reserving_get, retrying_get
from tests.boards.fakes import never_sleeps, responding
from tests.support.logs import capturing_logs

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


def counting(
    *replies: httpx2.Response | Exception,
) -> tuple[httpx2.AsyncClient, list[httpx2.Request]]:
    """A client that also records every request it actually received."""
    remaining: Iterator[httpx2.Response | Exception] = iter(replies)
    requests: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        reply = next(remaining)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle)), requests


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def clear(database: Database) -> None:
        async with database.session() as session:
            await session.execute(delete(SourceQuotaUsage))
            await session.commit()

    async def go() -> None:
        database = Database(database_url)
        try:
            await clear(database)
            await test(database)
        finally:
            await clear(database)
            await database.dispose()

    asyncio.run(go())


async def call_reserving_get(
    database: Database,
    quota: Quota,
    http_client: httpx2.AsyncClient,
    *,
    max_attempts: int = 3,
    retry_backoff_seconds: float = 0.0,
    sleeper: Callable[[float], Awaitable[None]] = never_sleeps,
) -> httpx2.Response:
    async with database.session() as session:
        response = await reserving_get(
            session,
            SOURCE_KEY,
            quota,
            http_client,
            "https://example.test/api",
            params={"page": "1"},
            timeout_seconds=5.0,
            max_attempts=max_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
            sleeper=sleeper,
            subject=SUBJECT,
        )
        await session.commit()
        return response


@pytest.mark.integration
def test_reserving_get_refuses_without_a_request_when_the_budget_is_spent(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        quota = Quota(per_day=1)
        async with database.session() as session:
            assert await reserve(session, SOURCE_KEY, quota=quota) is True
            await session.commit()

        http_client, requests = counting(httpx2.Response(200))
        try:
            with pytest.raises(QuotaExceeded):
                await call_reserving_get(database, quota, http_client)
        finally:
            await http_client.aclose()

        assert requests == []

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_reserving_get_makes_exactly_one_request_when_the_budget_is_not_spent(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        http_client, requests = counting(httpx2.Response(200, json={"ok": True}))
        try:
            response = await call_reserving_get(database, Quota(per_day=1), http_client)
        finally:
            await http_client.aclose()

        assert response.status_code == 200
        assert len(requests) == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_retry_inside_reserving_get_does_not_reserve_twice(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        sleeper, slept = recording()
        http_client, requests = counting(rate_limited("0"), httpx2.Response(200))
        try:
            response = await call_reserving_get(
                database, Quota(per_day=1), http_client, sleeper=sleeper
            )
        finally:
            await http_client.aclose()

        assert response.status_code == 200
        # Two HTTP requests from the one retried call, but only one reservation.
        assert len(requests) == 2
        assert slept == [0.0]

        async with database.session() as session:
            assert await used_today(session, SOURCE_KEY) == 1

    run_database_test(database_url, exercise)


def test_a_url_carrying_a_secret_produces_no_log_record_containing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`retrying_get` logs nothing today, so this is a regression guard: the
    moment a log line is added here without following the comment above it,
    this is the test that is meant to catch a credential riding along in the
    URL or the headers."""
    monkeypatch.setattr(logging_support, "_registered_secrets", set())
    secret = "SECRETVALUE-app-key-0123456789"
    register_secrets([secret])
    install_secret_filter()

    async def run() -> httpx2.Response:
        http_client = responding(httpx2.Response(200, json={"ok": True}))
        try:
            return await retrying_get(
                http_client,
                f"https://example.test/api?app_key={secret}",
                params={"app_key": secret},
                headers={"authorization": f"Bearer {secret}"},
                timeout_seconds=5.0,
                max_attempts=3,
                retry_backoff_seconds=0.0,
                sleeper=never_sleeps,
                source_key=SOURCE_KEY,
                subject=SUBJECT,
            )
        finally:
            await http_client.aclose()

    with capturing_logs("job_ingestion") as messages:
        response = asyncio.run(run())

    assert response.status_code == 200
    assert secret not in "\n".join(messages)


def test_a_url_carrying_a_secret_produces_no_log_record_when_a_rate_limit_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logging_support, "_registered_secrets", set())
    secret = "SECRETVALUE-rate-limited-987654321"
    register_secrets([secret])
    install_secret_filter()

    async def run() -> httpx2.Response:
        http_client = responding(rate_limited("0"), httpx2.Response(200, json={"ok": True}))
        try:
            return await retrying_get(
                http_client,
                f"https://example.test/api?app_key={secret}",
                params={"app_key": secret},
                headers={"authorization": f"Bearer {secret}"},
                timeout_seconds=5.0,
                max_attempts=3,
                retry_backoff_seconds=0.0,
                sleeper=never_sleeps,
                source_key=SOURCE_KEY,
                subject=SUBJECT,
            )
        finally:
            await http_client.aclose()

    with capturing_logs("job_ingestion") as messages:
        response = asyncio.run(run())

    assert response.status_code == 200
    assert secret not in "\n".join(messages)


def test_a_url_carrying_a_secret_produces_no_log_record_when_the_request_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logging_support, "_registered_secrets", set())
    secret = "SECRETVALUE-transport-error-135792468"
    register_secrets([secret])
    install_secret_filter()

    async def run() -> None:
        http_client = responding(*[httpx2.ConnectError("no route")] * 3)
        try:
            with pytest.raises(SourceUnavailableError):
                await retrying_get(
                    http_client,
                    f"https://example.test/api?app_key={secret}",
                    params={"app_key": secret},
                    headers={"authorization": f"Bearer {secret}"},
                    timeout_seconds=5.0,
                    max_attempts=3,
                    retry_backoff_seconds=0.0,
                    sleeper=never_sleeps,
                    source_key=SOURCE_KEY,
                    subject=SUBJECT,
                )
        finally:
            await http_client.aclose()

    with capturing_logs("job_ingestion") as messages:
        asyncio.run(run())

    assert secret not in "\n".join(messages)
