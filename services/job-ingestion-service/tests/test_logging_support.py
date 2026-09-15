"""Keeping credential values out of every log line."""

import logging

import pytest

from job_ingestion import logging_support
from job_ingestion.logging_support import (
    MINIMUM_SECRET_LENGTH,
    SecretFilter,
    install_secret_filter,
    register_secrets,
)
from tests.support.logs import capturing_logs

LOGGER_NAME = "job_ingestion.logging_support_test"


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
