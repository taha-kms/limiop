"""Keeping credential values out of every log line."""

import logging
from collections.abc import Callable

import pytest

from job_ingestion import logging_support
from job_ingestion.logging_support import (
    MINIMUM_SECRET_LENGTH,
    SecretFilter,
    install_secret_filter,
    register_secrets,
)
from tests.support.logs import capturing_logs, preserving_secret_filter

LOGGER_NAME = "job_ingestion.logging_support_test"
TRACEBACK_HEADER = "Traceback (most recent call last)"
STACK_HEADER = "Stack (most recent call last)"


@pytest.fixture(autouse=True)
def _no_secrets_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with nothing registered, regardless of test order.

    `_registered_secrets` is process-global by design -- a source registers
    its values once and every logger in the process benefits -- so a test
    that wants a clean slate, or wants to prove the empty state does nothing,
    has to force it rather than rely on being first.
    """
    monkeypatch.setattr(logging_support, "_registered_secrets", set())


def test_a_registered_secret_is_redacted_in_the_message() -> None:
    secret = "abcdef1234-embedded-in-message"
    register_secrets([secret])
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info(f"fetched with key {secret}")

    assert messages == ["fetched with key [redacted]"]
    assert secret not in "\n".join(messages)


def test_a_registered_secret_is_redacted_in_a_positional_argument() -> None:
    secret = "abcdef1234-in-positional-arg"
    register_secrets([secret])
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("fetched with key %s", secret)

    assert messages == ["fetched with key [redacted]"]
    assert secret not in "\n".join(messages)


def test_a_registered_secret_is_redacted_in_a_mapping_argument() -> None:
    secret = "abcdef1234-in-mapping-arg"
    register_secrets([secret])
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("fetched with key %(key)s", {"key": secret})

    assert messages == ["fetched with key [redacted]"]
    assert secret not in "\n".join(messages)


def test_a_non_string_argument_passes_through_untouched() -> None:
    secret = "abcdef1234-untouched-number"
    register_secrets([secret])
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("fetched %s pages", 3)

    assert messages == ["fetched 3 pages"]


def test_an_exception_argument_is_redacted_when_its_text_carries_a_secret() -> None:
    secret = "abcdef1234-inside-an-exception"
    register_secrets([secret])
    install_secret_filter()

    error = RuntimeError(f"could not reach https://example.test/?key={secret}")
    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("request failed: %s", error)

    assert messages == ["request failed: could not reach https://example.test/?key=[redacted]"]
    assert secret not in "\n".join(messages)


def test_an_exception_argument_without_a_secret_passes_through_untouched() -> None:
    register_secrets(["abcdef1234-not-in-this-exception"])
    install_secret_filter()

    error = RuntimeError("connection refused")
    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("request failed: %s", error)

    assert messages == ["request failed: connection refused"]


def test_a_purely_numeric_argument_is_never_redacted_and_formats_with_percent_d() -> None:
    numeric_secret = "12345678"
    assert len(numeric_secret) >= MINIMUM_SECRET_LENGTH
    register_secrets([numeric_secret])
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("count is %d", int(numeric_secret))

    assert messages == [f"count is {numeric_secret}"]


def test_an_argument_whose_str_raises_is_passed_through_unchanged() -> None:
    register_secrets(["abcdef1234-irrelevant-to-this-test"])

    class Explodes:
        def __str__(self) -> str:
            raise ValueError("boom")

    explodes = Explodes()
    record = logging.LogRecord(
        name=LOGGER_NAME,
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="value: %s",
        args=(explodes,),
        exc_info=None,
    )

    kept = SecretFilter().filter(record)

    assert kept is True
    assert record.args == (explodes,)


def test_a_short_value_is_never_registered() -> None:
    short_secret = "1234567"
    assert len(short_secret) < MINIMUM_SECRET_LENGTH
    register_secrets([short_secret])
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("code is %s", short_secret)

    assert messages == [f"code is {short_secret}"]


def test_a_minimum_length_value_is_registered() -> None:
    exact_length_secret = "12345678"
    assert len(exact_length_secret) == MINIMUM_SECRET_LENGTH
    register_secrets([exact_length_secret])
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("code is %s", exact_length_secret)

    assert messages == ["code is [redacted]"]


def test_nothing_registered_leaves_a_record_untouched() -> None:
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("nothing registered yet: %s", "not-a-secret")

    assert messages == ["nothing registered yet: not-a-secret"]


def test_a_non_string_message_passes_through_untouched() -> None:
    register_secrets(["abcdef1234-not-in-this-record"])
    install_secret_filter()

    class Sentinel:
        def __str__(self) -> str:
            return "a non-string message"

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info(Sentinel())

    assert messages == ["a non-string message"]


def test_a_record_without_any_arguments_is_left_alone() -> None:
    register_secrets(["abcdef1234-not-present-here"])
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("a plain message with no arguments")

    assert messages == ["a plain message with no arguments"]


def test_a_record_with_neither_tuple_nor_mapping_arguments_is_left_alone() -> None:
    register_secrets(["abcdef1234-not-present-either"])
    record = logging.LogRecord(
        name=LOGGER_NAME,
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="already a plain string",
        args=None,
        exc_info=None,
    )

    kept = SecretFilter().filter(record)

    assert kept is True
    assert record.getMessage() == "already a plain string"


def test_secret_filter_redacts_a_record_passed_to_it_directly() -> None:
    register_secrets(["abcdef1234-direct-filter-usage"])
    record = logging.LogRecord(
        name=LOGGER_NAME,
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="key: %s",
        args=("abcdef1234-direct-filter-usage",),
        exc_info=None,
    )

    kept = SecretFilter().filter(record)

    assert kept is True
    assert record.getMessage() == "key: [redacted]"


def test_installing_twice_adds_one_filter_to_the_root_logger() -> None:
    install_secret_filter()
    install_secret_filter()

    secret_filters = [f for f in logging.getLogger().filters if isinstance(f, SecretFilter)]
    assert len(secret_filters) == 1


def test_capturing_logs_returns_what_was_emitted_with_no_secrets_registered() -> None:
    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info("plain message, nothing to redact")

    assert messages == ["plain message, nothing to redact"]


def test_capturing_logs_stops_capturing_once_the_context_exits() -> None:
    with capturing_logs(LOGGER_NAME) as messages:
        pass

    logging.getLogger(f"{LOGGER_NAME}.child").info("emitted after the context closed")

    assert messages == []


def _record(msg: str, *, sinfo: str | None = None) -> logging.LogRecord:
    return logging.LogRecord(
        name=LOGGER_NAME,
        level=logging.ERROR,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
        sinfo=sinfo,
    )


def _log_with_traceback(logger: logging.Logger, secret: str) -> None:
    try:
        raise RuntimeError(f"could not reach https://example.test/?key={secret}")
    except RuntimeError:
        logger.exception("request failed")


def _log_with_args(logger: logging.Logger, secret: str) -> None:
    logger.info("fetched with key %s", secret)


def _log_with_f_string(logger: logging.Logger, secret: str) -> None:
    logger.info(f"fetched with key {secret}")


REDACTED_TRACEBACK_TAIL = "RuntimeError: could not reach https://example.test/?key=[redacted]"


@pytest.mark.parametrize(
    ("emit", "propagate", "expected_fragments"),
    [
        pytest.param(_log_with_args, True, ("fetched with key [redacted]",), id="args"),
        pytest.param(_log_with_f_string, True, ("fetched with key [redacted]",), id="f-string"),
        pytest.param(_log_with_args, False, ("fetched with key [redacted]",), id="propagate-false"),
        pytest.param(
            _log_with_traceback,
            True,
            (TRACEBACK_HEADER, REDACTED_TRACEBACK_TAIL),
            id="traceback",
        ),
        pytest.param(
            _log_with_traceback,
            False,
            (TRACEBACK_HEADER, REDACTED_TRACEBACK_TAIL),
            id="propagate-false-traceback",
        ),
    ],
)
def test_no_captured_line_carries_a_registered_secret(
    emit: Callable[[logging.Logger, str], None],
    propagate: bool,
    expected_fragments: tuple[str, ...],
) -> None:
    """The shapes from the report: `%s` arguments, an f-string, a logger that
    never reaches the root logger's filter, and a traceback whose final line
    carries the exception message. Each must come out with the secret gone
    and the rest of the line -- the traceback included -- still there."""
    secret = "abcdef1234-must-never-be-captured"
    register_secrets([secret])
    install_secret_filter()
    logger = logging.getLogger(f"{LOGGER_NAME}.shape")
    logger.propagate = propagate

    try:
        with capturing_logs(logger.name) as messages:
            emit(logger, secret)
    finally:
        logger.propagate = True

    output = "\n".join(messages)
    assert secret not in output
    for fragment in expected_fragments:
        assert fragment in output


def test_a_traceback_cached_by_one_handler_is_still_redacted_for_the_next() -> None:
    """`Formatter.format` stores the traceback text on `record.exc_text` the
    first time any handler formats it and every later handler reuses that
    cache, so the second handler here never formats the exception itself."""
    secret = "abcdef1234-cached-between-handlers"
    register_secrets([secret])
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as first, capturing_logs(LOGGER_NAME) as second:
        _log_with_traceback(logging.getLogger(f"{LOGGER_NAME}.child"), secret)

    assert first == second
    output = "\n".join(first)
    assert secret not in output
    assert TRACEBACK_HEADER in output
    assert REDACTED_TRACEBACK_TAIL in output


def test_a_secret_is_redacted_when_stack_info_is_requested() -> None:
    secret = "abcdef1234-logged-with-stack-info"
    register_secrets([secret])
    install_secret_filter()

    with capturing_logs(LOGGER_NAME) as messages:
        logging.getLogger(f"{LOGGER_NAME}.child").info(
            f"fetched with key {secret}", stack_info=True
        )

    output = "\n".join(messages)
    assert secret not in output
    assert output.startswith("fetched with key [redacted]")
    assert STACK_HEADER in output


def test_secret_filter_redacts_traceback_text_already_cached_on_a_record() -> None:
    secret = "abcdef1234-already-on-exc-text"
    register_secrets([secret])
    record = _record("request failed")
    record.exc_text = f"{TRACEBACK_HEADER}:\nRuntimeError: key={secret}"

    kept = SecretFilter().filter(record)

    assert kept is True
    assert record.exc_text == f"{TRACEBACK_HEADER}:\nRuntimeError: key=[redacted]"


def test_secret_filter_redacts_stack_info_carried_by_a_record() -> None:
    secret = "abcdef1234-already-in-stack-info"
    register_secrets([secret])
    record = _record("request failed", sinfo=f"{STACK_HEADER}:\n  key={secret}")

    kept = SecretFilter().filter(record)

    assert kept is True
    assert record.stack_info == f"{STACK_HEADER}:\n  key=[redacted]"


def test_installing_twice_wraps_the_traceback_formatter_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = logging.Formatter.formatException
    with preserving_secret_filter():
        monkeypatch.setattr(logging_support, "_installed", False)
        install_secret_filter()
        wrapped = logging.Formatter.formatException
        install_secret_filter()

        assert logging.Formatter.formatException is wrapped

    assert wrapped is not original
    assert getattr(wrapped, "__wrapped__", None) is original


def test_preserving_secret_filter_restores_the_traceback_formatter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = logging.Formatter.formatException
    with preserving_secret_filter():
        monkeypatch.setattr(logging_support, "_installed", False)
        install_secret_filter()

        assert logging.Formatter.formatException is not original

    assert logging.Formatter.formatException is original
