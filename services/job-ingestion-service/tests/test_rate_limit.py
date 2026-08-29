"""Reading how long a provider wants to be left alone."""

from datetime import UTC, datetime, timedelta

import httpx2
import pytest

from job_ingestion.rate_limit import (
    MAXIMUM_WAIT_SECONDS,
    RATE_LIMITED,
    is_rate_limited,
    retry_delay,
)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
FALLBACK = 0.5


def limited(**headers: str) -> httpx2.Response:
    return httpx2.Response(RATE_LIMITED, headers=headers)


def test_only_a_rate_limit_is_a_rate_limit() -> None:
    assert is_rate_limited(limited())
    assert not is_rate_limited(httpx2.Response(503))
    assert not is_rate_limited(httpx2.Response(200))


def test_a_count_of_seconds_is_honoured() -> None:
    assert retry_delay(limited(**{"retry-after": "7"}), fallback=FALLBACK) == 7.0


def test_an_http_date_is_honoured() -> None:
    later = NOW + timedelta(seconds=30)
    header = later.strftime("%a, %d %b %Y %H:%M:%S GMT")

    assert retry_delay(limited(**{"retry-after": header}), fallback=FALLBACK, now=NOW) == 30.0


def test_a_date_without_a_zone_is_read_as_gmt_rather_than_local() -> None:
    """Reading it as local time would shift the wait by the server's offset."""
    later = NOW + timedelta(seconds=45)
    header = later.strftime("%a, %d %b %Y %H:%M:%S")

    assert retry_delay(limited(**{"retry-after": header}), fallback=FALLBACK, now=NOW) == 45.0


@pytest.mark.parametrize("header", ["soon", "", "-5", "0", "Mon, 99 Xxx 2026 99:99:99 GMT"])
def test_an_unusable_value_falls_back_rather_than_retrying_immediately(header: str) -> None:
    """A malformed header is the provider being unhelpful, not permission."""
    assert retry_delay(limited(**{"retry-after": header}), fallback=FALLBACK) == FALLBACK


def test_a_date_already_in_the_past_falls_back() -> None:
    header = (NOW - timedelta(minutes=5)).strftime("%a, %d %b %Y %H:%M:%S GMT")

    assert retry_delay(limited(**{"retry-after": header}), fallback=FALLBACK, now=NOW) == FALLBACK


def test_no_header_at_all_uses_the_callers_own_backoff() -> None:
    assert retry_delay(limited(), fallback=FALLBACK) == FALLBACK


def test_an_unreasonable_wait_is_capped() -> None:
    """A run that sleeps past its next scheduled run is worse than one that
    reports it did not reach the end."""
    assert retry_delay(limited(**{"retry-after": "3600"}), fallback=FALLBACK) == (
        MAXIMUM_WAIT_SECONDS
    )
