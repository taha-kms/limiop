"""Provider-independent job ingestion boundaries."""

from app.modules.ingestion.contracts import (
    IngestionStage,
    IngestionSummary,
    JobRecordNormalizer,
    JobRecordValidator,
    JobSourceClient,
    RawPage,
    RawRecord,
    RecordFailure,
    RecordOutcome,
)
from app.modules.ingestion.errors import (
    IngestionError,
    RecordValidationError,
    SourceResponseError,
    SourceUnavailableError,
)

__all__ = [
    "IngestionError",
    "IngestionStage",
    "IngestionSummary",
    "JobRecordNormalizer",
    "JobRecordValidator",
    "JobSourceClient",
    "RawPage",
    "RawRecord",
    "RecordFailure",
    "RecordOutcome",
    "RecordValidationError",
    "SourceResponseError",
    "SourceUnavailableError",
]
