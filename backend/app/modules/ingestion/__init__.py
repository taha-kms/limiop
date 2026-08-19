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
from app.modules.ingestion.deduplication import (
    DeduplicationDecision,
    DeduplicationOutcome,
    MatchBasis,
    decide,
)
from app.modules.ingestion.errors import (
    IngestionError,
    RecordValidationError,
    SourceResponseError,
    SourceUnavailableError,
)

__all__ = [
    "DeduplicationDecision",
    "DeduplicationOutcome",
    "IngestionError",
    "IngestionStage",
    "IngestionSummary",
    "JobRecordNormalizer",
    "JobRecordValidator",
    "JobSourceClient",
    "MatchBasis",
    "RawPage",
    "RawRecord",
    "RecordFailure",
    "RecordOutcome",
    "RecordValidationError",
    "SourceResponseError",
    "SourceUnavailableError",
    "decide",
]
