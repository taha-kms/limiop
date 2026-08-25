"""Failures that ingestion stages raise instead of swallowing.

A failure that makes the rest of a page meaningless is raised. A failure that
only invalidates one external record is reported as a value, so one bad record
cannot discard the good records fetched alongside it. See `contracts.py`.
"""


class IngestionError(Exception):
    """Base class for every expected ingestion failure."""

    def __init__(self, source_key: str, message: str) -> None:
        super().__init__(f"{source_key}: {message}")
        self.source_key = source_key
        self.message = message


class SourceUnavailableError(IngestionError):
    """The provider could not be reached.

    Raised for timeouts, connection failures, and other transport problems. The
    request may succeed later, so callers may retry within a bounded budget.
    """


class SourceResponseError(IngestionError):
    """The provider answered with something unusable.

    Raised for non-success status codes and bodies that are not the documented
    shape. Retrying the same request is not expected to help.
    """

    def __init__(self, source_key: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(source_key, message)
        self.status_code = status_code


class RecordValidationError(IngestionError):
    """One external record cannot be trusted.

    Raised by a validator for a single record. Callers catch this per record and
    record a failure, rather than letting it abort the batch.
    """

    def __init__(self, source_key: str, message: str, *, source_job_id: str | None = None) -> None:
        super().__init__(source_key, message)
        self.source_job_id = source_job_id
