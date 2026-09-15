"""Capturing formatted log output for a test to inspect."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager


class _ListHandler(logging.Handler):
    def __init__(self, sink: list[str]) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(self.format(record))


@contextmanager
def capturing_logs(logger_name: str) -> Iterator[list[str]]:
    """Capture every formatted message `logger_name` and its descendants emit.

    A handler attached here sees what any globally installed filter or log
    record factory already did to the record, exactly as a real handler
    would, because those run before a handler formats anything.
    """
    messages: list[str] = []
    logger = logging.getLogger(logger_name)
    handler = _ListHandler(messages)
    handler.setLevel(logging.DEBUG)
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield messages
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
