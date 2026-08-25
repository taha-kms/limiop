"""Provider-independent job ingestion boundaries."""

from job_ingestion.config import Settings, get_settings
from job_ingestion.contracts import (
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
from job_ingestion.deduplication import (
    DeduplicationDecision,
    DeduplicationOutcome,
    MatchBasis,
    decide,
)
from job_ingestion.errors import (
    IngestionError,
    RecordValidationError,
    SourceResponseError,
    SourceUnavailableError,
)
from job_ingestion.persistence import (
    PersistenceResult,
    SourceRegistration,
    persist_job,
)
from job_ingestion.pipeline import IngestionRun

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
    "Settings",
    "SourceRegistration",
    "SourceResponseError",
    "SourceUnavailableError",
    "decide",
    "get_settings",
    "persist_job",
]
