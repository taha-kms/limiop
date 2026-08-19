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
from app.modules.ingestion.persistence import (
    PersistenceResult,
    SourceRegistration,
    persist_job,
)
from app.modules.ingestion.pipeline import IngestionRun

__all__ = [
    "DeduplicationDecision",
    "DeduplicationOutcome",
    "IngestionError",
    "IngestionRun",
    "IngestionStage",
    "IngestionSummary",
    "JobRecordNormalizer",
    "JobRecordValidator",
    "JobSourceClient",
    "MatchBasis",
    "PersistenceResult",
    "RawPage",
    "RawRecord",
    "RecordFailure",
    "RecordOutcome",
    "RecordValidationError",
    "SourceRegistration",
    "SourceResponseError",
    "SourceUnavailableError",
    "decide",
    "persist_job",
]
