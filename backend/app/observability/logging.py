"""Structured application logging.

One JSON object per line, because the alternative is a format that is readable
by a person on one machine and by nothing at all once it reaches a log store.

Every record carries the correlation identifier of the request that produced
it, taken from a context variable rather than passed down through call
arguments — logging is a cross-cutting concern and threading an identifier
through every signature to satisfy it is how that concern leaks everywhere.

Nothing here formats a message with request data. A logged value is a field,
so a value containing a brace, a quote, or a newline cannot reshape the record
it appears in.
"""

import json
import logging
from contextvars import ContextVar
from typing import Any

# The fields every record carries, and the only ones a reader should rely on.
CORE_FIELDS = ("time", "level", "logger", "message", "correlation_id")

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Anything a formatter must not copy out of a record's extras. The request path
# and method are safe and useful; a body, a header, and a cookie are none of
# those things, and the cheapest way not to log one is to have no way to.
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "asctime",
    "message",
    "taskName",
}


class JSONFormatter(logging.Formatter):
    """Render one record as a single JSON object.

    Extras are included, so a caller adds context by naming it rather than by
    building a sentence. An exception becomes a `error.type` and a
    `error.message`; the traceback is kept because it names our own code, and
    the message is whatever the raiser wrote, which is why nothing in this
    application raises with a credential in it.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id.get(),
        }
        payload.update(
            {key: value for key, value in record.__dict__.items() if key not in _RESERVED}
        )
        if record.exc_info and record.exc_info[0] is not None:
            payload["error.type"] = record.exc_info[0].__name__
            payload["error.message"] = str(record.exc_info[1])
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Send every record through one JSON handler.

    Replaces existing handlers rather than adding to them, so a record is
    emitted once. Uvicorn installs its own on import, and leaving those in
    place produces every line twice in two different formats.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
