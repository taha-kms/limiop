"""Giving every request an identifier, and logging what happened to it."""

import logging
import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.logging import correlation_id

logger = logging.getLogger("app.request")

CORRELATION_HEADER = "x-correlation-id"

# A client may supply one so a trace spans more than this service, but it is
# validated rather than trusted: an identifier is echoed into every log line
# this request writes, and an unbounded one from the outside is a way to write
# whatever you like into them.
_ACCEPTABLE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# A liveness probe runs every few seconds forever. Logging it at info buries
# everything else, which is the failure mode of logging that nobody turns off
# because it is technically working.
_QUIET_PATHS = frozenset({"/health", "/health/ready"})


def identifier_from(request: Request) -> str:
    supplied = request.headers.get(CORRELATION_HEADER)
    return supplied if supplied and _ACCEPTABLE.match(supplied) else str(uuid4())


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Correlate one request, and record its outcome once."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        identifier = identifier_from(request)
        token = correlation_id.set(identifier)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Logged here because nothing downstream will: the exception is
            # about to become a 500 that carries no explanation by design.
            logger.exception(
                "request failed",
                extra={
                    "http.method": request.method,
                    "http.route": request.url.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise
        finally:
            correlation_id.reset(token)

        response.headers[CORRELATION_HEADER] = identifier
        if request.url.path not in _QUIET_PATHS:
            # A 4xx is the client being told no, which is the API working.
            # Only a 5xx is this application's problem.
            level = logging.ERROR if response.status_code >= 500 else logging.INFO
            logger.log(
                level,
                "request handled",
                extra={
                    "http.method": request.method,
                    "http.route": request.url.path,
                    "http.status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "correlation_id": identifier,
                },
            )
        return response
