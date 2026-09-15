"""Capturing formatted log output for a test to inspect."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from job_ingestion import logging_support


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


@contextmanager
def preserving_secret_filter() -> Iterator[None]:
    """Undo whatever a real call to `install_secret_filter` does inside.

    `install_secret_filter` is meant to run once and stay installed for the
    life of the process, so it mutates three pieces of global state together:
    the module's own `_installed` flag, the shared log record factory, and
    the root logger's filter list. A test that provokes a real installation
    -- as opposed to one that stubs `install_secret_filter` out -- has to put
    all three back, and only all three together: restoring the factory and
    the root filters while leaving `_installed` set would make every later
    real installation in the process a silent no-op, since the flag would
    claim the work was already done while the actual wrap had been erased.
    """
    installed = logging_support._installed
    factory = logging.getLogRecordFactory()
    root_filters = list(logging.getLogger().filters)
    try:
        yield
    finally:
        logging_support._installed = installed
        logging.setLogRecordFactory(factory)
        logging.getLogger().filters = root_filters
