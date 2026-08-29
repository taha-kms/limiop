"""Reading how long a provider wants to be left alone.

A rate limit is the most predictable non-200 a public API returns and the only
transient one that is not a transport error, which made it the one failure the
clients did not retry. Two consecutive runs against the live board stopped at
different pages, ingesting 1450 and then 1150 records, so how much of a source
was read depended on how the provider felt about the traffic.
"""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx2

RATE_LIMITED = 429

# A provider may ask for an hour. Waiting is not the same as being useful, and a
# scheduled run that sleeps past its next scheduled run is worse than one that
# gives up and reports it did not reach the end. Capped, and the cap is why an
# unreasonable ask ends in exhausted attempts rather than a stalled process.
MAXIMUM_WAIT_SECONDS = 60.0


def is_rate_limited(response: httpx2.Response) -> bool:
    return response.status_code == RATE_LIMITED


def retry_delay(
    response: httpx2.Response,
    *,
    fallback: float,
    now: datetime | None = None,
) -> float:
    """How long to wait before asking again.

    `Retry-After` in either of its forms — a count of seconds, or an HTTP date.
    Anything unparseable, negative, or already past falls back to the caller's
    own backoff rather than to zero: a malformed header is the provider being
    unhelpful, not permission to retry immediately.
    """
    header = response.headers.get("retry-after")
    if header is None:
        return fallback

    stripped = header.strip()
    try:
        seconds = float(stripped)
    except ValueError:
        seconds = _seconds_until(stripped, now or datetime.now(UTC))

    if seconds <= 0:
        return fallback
    return min(seconds, MAXIMUM_WAIT_SECONDS)


def _seconds_until(value: str, now: datetime) -> float:
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return -1.0
    if moment.tzinfo is None:
        # RFC 9110 dates are GMT; a parser that returns naive means the zone
        # was absent, and reading it as local time would shift the wait.
        moment = moment.replace(tzinfo=UTC)
    return (moment - now).total_seconds()
