import pytest

from job_ingestion.errors import (
    IngestionError,
    RecordValidationError,
    SourceResponseError,
    SourceUnavailableError,
)

SOURCE_KEY = "arbeitnow"


@pytest.mark.parametrize(
    "error_type",
    [SourceUnavailableError, SourceResponseError, RecordValidationError],
)
def test_every_ingestion_failure_shares_one_base(error_type: type[IngestionError]) -> None:
    error = error_type(SOURCE_KEY, "something went wrong")

    assert isinstance(error, IngestionError)
    assert error.source_key == SOURCE_KEY
    assert error.message == "something went wrong"


def test_failure_text_names_the_source() -> None:
    error = SourceUnavailableError(SOURCE_KEY, "read timed out after 10s")

    assert str(error) == "arbeitnow: read timed out after 10s"


def test_transport_and_response_failures_are_distinguishable() -> None:
    unavailable = SourceUnavailableError(SOURCE_KEY, "connection reset")
    unusable = SourceResponseError(SOURCE_KEY, "unexpected status", status_code=503)

    assert not isinstance(unavailable, SourceResponseError)
    assert not isinstance(unusable, SourceUnavailableError)


def test_response_failure_keeps_the_status_code() -> None:
    error = SourceResponseError(SOURCE_KEY, "unexpected status", status_code=429)

    assert error.status_code == 429


def test_response_failure_allows_no_status_code() -> None:
    error = SourceResponseError(SOURCE_KEY, "body is not valid JSON")

    assert error.status_code is None


def test_record_failure_identifies_the_record_when_it_can() -> None:
    error = RecordValidationError(SOURCE_KEY, "slug is required", source_job_id="external-42")

    assert error.source_job_id == "external-42"


def test_record_failure_tolerates_an_unidentifiable_record() -> None:
    error = RecordValidationError(SOURCE_KEY, "record is not an object")

    assert error.source_job_id is None


def test_a_record_failure_is_not_confused_with_a_transport_failure() -> None:
    with pytest.raises(RecordValidationError):
        raise RecordValidationError(SOURCE_KEY, "slug is required")

    with pytest.raises(IngestionError):
        raise SourceUnavailableError(SOURCE_KEY, "read timed out")
