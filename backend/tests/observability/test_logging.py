"""Structured logging and request correlation."""

import json
import logging
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability.logging import CORE_FIELDS, JSONFormatter, configure_logging, correlation_id
from app.observability.middleware import CORRELATION_HEADER, CorrelationMiddleware, identifier_from


def rendered(record: logging.LogRecord) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(JSONFormatter().format(record))
    return payload


def request_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Only this application's request log.

    The test client logs its own line through httpx, and caplog collects at the
    root, so filtering by logger is what makes "logged once" mean once.
    """
    return [record for record in caplog.records if record.name == "app.request"]


def make_record(message: str = "hello", **extra: Any) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, message, None, None)
    record.__dict__.update(extra)
    return record


def test_every_record_carries_the_documented_core_fields() -> None:
    payload = rendered(make_record())

    assert set(CORE_FIELDS) <= set(payload)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello"


def test_a_record_written_inside_a_request_carries_its_identifier() -> None:
    token = correlation_id.set("abc-123")
    try:
        assert rendered(make_record())["correlation_id"] == "abc-123"
    finally:
        correlation_id.reset(token)


def test_a_record_written_outside_a_request_says_so_rather_than_inventing_one() -> None:
    assert rendered(make_record())["correlation_id"] is None


def test_extras_become_fields_rather_than_being_formatted_into_the_message() -> None:
    """A value with a brace or a quote in it cannot reshape the record."""
    payload = rendered(make_record('a "quoted" {brace}', **{"http.route": "/jobs"}))

    assert payload["http.route"] == "/jobs"
    assert payload["message"] == 'a "quoted" {brace}'


def test_an_exception_is_named_rather_than_pasted_into_the_message() -> None:
    try:
        raise ValueError("something went wrong")
    except ValueError:
        record = logging.LogRecord(
            "app.test", logging.ERROR, __file__, 1, "failed", None, __import__("sys").exc_info()
        )

    payload = rendered(record)

    assert payload["error.type"] == "ValueError"
    assert payload["error.message"] == "something went wrong"


def test_the_record_is_one_line_of_json() -> None:
    text = JSONFormatter().format(make_record("line one\nline two"))

    assert "\n" not in text
    assert json.loads(text)["message"] == "line one\nline two"


def test_configuring_logging_leaves_exactly_one_handler() -> None:
    """Uvicorn installs its own on import, and two handlers print every line
    twice in two different formats."""
    configure_logging()
    configure_logging()

    assert len(logging.getLogger().handlers) == 1
    assert logging.getLogger("uvicorn.access").handlers == []


def test_uvicorns_own_access_log_is_silenced() -> None:
    """It logs a line per request with no correlation identifier and no notion
    of which paths are probes, so a liveness check appears there however quiet
    our own request log is."""
    configure_logging()

    assert logging.getLogger("uvicorn.access").level == logging.WARNING


@pytest.fixture
def instrumented() -> TestClient:
    application = FastAPI()
    application.add_middleware(CorrelationMiddleware)

    @application.get("/ok")
    def ok() -> dict[str, str]:
        return {"correlation_id": correlation_id.get() or ""}

    @application.get("/boom")
    def boom() -> None:
        raise RuntimeError("deliberate")

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(application, raise_server_exceptions=False)


def test_a_request_gets_an_identifier_and_the_response_carries_it(
    instrumented: TestClient,
) -> None:
    response = instrumented.get("/ok")

    assert response.status_code == 200
    assert response.headers[CORRELATION_HEADER] == response.json()["correlation_id"]


def test_a_clients_identifier_is_reused_so_a_trace_spans_services(
    instrumented: TestClient,
) -> None:
    response = instrumented.get("/ok", headers={CORRELATION_HEADER: "from-the-gateway"})

    assert response.headers[CORRELATION_HEADER] == "from-the-gateway"


@pytest.mark.parametrize(
    "supplied",
    ["", "has spaces", "x" * 65, "line\nbreak", "semi;colon"],
)
def test_an_unusable_identifier_is_replaced_rather_than_echoed(
    instrumented: TestClient, supplied: str
) -> None:
    """It is written into every log line this request produces, so an
    unbounded one from outside writes whatever it likes into them."""
    response = instrumented.get("/ok", headers={CORRELATION_HEADER: supplied})

    assert response.headers[CORRELATION_HEADER] != supplied


def test_two_requests_do_not_share_an_identifier(instrumented: TestClient) -> None:
    first = instrumented.get("/ok").headers[CORRELATION_HEADER]
    second = instrumented.get("/ok").headers[CORRELATION_HEADER]

    assert first != second


def test_a_liveness_probe_is_not_logged(
    instrumented: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """It runs every few seconds forever and would bury everything else."""
    with caplog.at_level(logging.INFO, logger="app.request"):
        instrumented.get("/health")

    assert request_records(caplog) == []


def test_a_handled_request_is_logged_once_with_its_outcome(
    instrumented: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.request"):
        instrumented.get("/ok")

    records = request_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.INFO
    assert record.__dict__["http.status"] == 200
    assert record.__dict__["http.route"] == "/ok"


def test_a_failing_request_is_logged_as_an_error_with_the_exception(
    instrumented: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.request"):
        assert instrumented.get("/boom").status_code == 500

    records = request_records(caplog)
    assert [record.getMessage() for record in records] == ["request failed"]
    assert rendered(records[0])["error.type"] == "RuntimeError"


def test_a_rejected_request_is_not_this_applications_error(
    instrumented: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A 404 is the API working. Logging it at error is how alerts get ignored."""
    with caplog.at_level(logging.INFO, logger="app.request"):
        instrumented.get("/nothing-here")

    assert [record.levelno for record in request_records(caplog)] == [logging.INFO]


def test_an_identifier_is_generated_when_none_is_supplied() -> None:
    from starlette.datastructures import Headers
    from starlette.requests import Request

    request = Request({"type": "http", "headers": Headers({}).raw, "method": "GET", "path": "/"})

    assert len(identifier_from(request)) == 36
