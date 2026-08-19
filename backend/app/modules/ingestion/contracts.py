"""Stage boundaries shared by every job provider.

Ingestion runs as four stages with explicit types between them:

    fetch     RawPage           untrusted provider JSON
    validate  provider record   typed, provider-shaped
    normalize NormalizedJob     canonical contract
    persist   RecordOutcome     what the database did

Each stage is a protocol so providers stay independently testable, and nothing
here imports a scheduler, a web framework, or a database session factory.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from app.modules.jobs.schemas import NormalizedJob

RawRecord = Mapping[str, Any]


class IngestionStage(StrEnum):
    """The stage a record was in when it failed."""

    FETCH = "fetch"
    VALIDATE = "validate"
    NORMALIZE = "normalize"
    PERSIST = "persist"


class RecordOutcome(StrEnum):
    """What persistence did with one normalized job."""

    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class RawPage:
    """One untrusted page of provider records."""

    records: tuple[RawRecord, ...]
    next_page: int | None = None

    @property
    def has_next_page(self) -> bool:
        return self.next_page is not None


@dataclass(frozen=True, slots=True)
class RecordFailure:
    """One record that could not be processed, kept as a value.

    Reasons are short operator-facing text. Never put a raw provider payload
    here: failures are logged, and provider data is untrusted.
    """

    stage: IngestionStage
    reason: str
    source_job_id: str | None = None


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    """The result of one ingestion run.

    Counts and failures are reported together so a run that processed most of a
    batch cannot be mistaken for a clean one.
    """

    source_key: str
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failures: tuple[RecordFailure, ...] = field(default_factory=tuple)

    @property
    def persisted(self) -> int:
        return self.created + self.updated

    @property
    def failed(self) -> int:
        return len(self.failures)

    @property
    def is_complete(self) -> bool:
        """Whether every fetched record reached a persistence outcome."""
        return self.fetched == self.persisted + self.skipped and not self.failures


@runtime_checkable
class JobSourceClient(Protocol):
    """Fetches untrusted pages from one provider."""

    @property
    def source_key(self) -> str: ...

    async def fetch_page(self, page: int) -> RawPage:
        """Return one page, or raise `SourceUnavailableError`/`SourceResponseError`."""
        ...


@runtime_checkable
class JobRecordValidator[ProviderRecordT](Protocol):
    """Turns one untrusted record into a typed provider record."""

    def validate(self, record: RawRecord) -> ProviderRecordT:
        """Return the typed record, or raise `RecordValidationError`."""
        ...


@runtime_checkable
class JobRecordNormalizer[ProviderRecordT](Protocol):
    """Maps one typed provider record onto the canonical contract."""

    def normalize(self, record: ProviderRecordT) -> NormalizedJob:
        """Return the canonical job, or raise `RecordValidationError`."""
        ...
