"""Retrying an HTTP GET the same way every ingestion client wants it retried.

Every client that walks a paginated JSON API copied the same loop: a
transport failure or a rate limit is worth a retry, up to a bounded number of
attempts, and anything else the provider answers is not. Kept here once so
the retry rule, and its wording, can only drift in one place rather than in
every client that needs it.
"""

from collections.abc import Awaitable, Callable, Mapping

import httpx2

from job_ingestion.errors import SourceUnavailableError
from job_ingestion.rate_limit import is_rate_limited, retry_delay


async def retrying_get(
    http_client: httpx2.AsyncClient,
    url: str,
    *,
    params: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float,
    max_attempts: int,
    retry_backoff_seconds: float,
    sleeper: Callable[[float], Awaitable[None]],
    source_key: str,
    subject: str,
) -> httpx2.Response:
    """GET `url`, retrying a transport failure or a rate limit.

    A rate limit is transient by definition and is the most predictable
    non-200 a public API returns, which made it the one transient failure
    that used to end a run where it stood. Any other answer -- success or
    failure -- is returned exactly as received: deciding what a status code
    or a body means is the caller's job, not this one's.

    `subject` names what is being fetched for the caller's error messages
    (a page number, a cursor, a board slug) -- this function does not know
    the provider's own vocabulary for what it is asking for.

    Exhausting the attempts raises, so a caller that never got an answer
    knows it, rather than being handed a response that was never received.
    """
    last_failure: SourceUnavailableError | None = None
    for attempt in range(1, max_attempts + 1):
        delay = retry_backoff_seconds
        try:
            response = await http_client.get(
                url, params=params, headers=headers, timeout=timeout_seconds
            )
        except httpx2.TimeoutException as error:
            last_failure = SourceUnavailableError(source_key, f"{subject} timed out: {error}")
        except httpx2.TransportError as error:
            last_failure = SourceUnavailableError(
                source_key, f"{subject} could not be reached: {error}"
            )
        else:
            if not is_rate_limited(response):
                return response
            last_failure = SourceUnavailableError(source_key, f"{subject} was rate limited")
            delay = retry_delay(response, fallback=delay)

        if attempt < max_attempts:
            await sleeper(delay)

    raise (
        last_failure
        if last_failure is not None
        else SourceUnavailableError(source_key, f"{subject} could not be fetched")
    )
