"""Stage boundaries shared by every job provider.

Ingestion runs as four stages with explicit types between them:

    fetch     RawPage           untrusted provider JSON
    validate  provider record   typed, provider-shaped
    normalize NormalizedJob     canonical contract
    persist   RecordOutcome     what the database did

Each stage is a protocol so providers stay independently testable, and nothing
here imports a scheduler, a web framework, or a database session factory.
"""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from job_ingestion.schemas import NormalizedJob

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
    # Whether the provider ran out of records to give, rather than the run
    # running out of room to take them. A client sets this only when it reached
    # the end of everything it was asked to read.
    reached_the_end: bool = False
    # Whether the run stopped because it hit its own record budget.
    stopped_at_budget: bool = False
    # The alias table every skill count below was produced under, or None when
    # no vocabulary was published and nothing was extracted.
    alias_version: str | None = None
    # Mentions resolved to one concept and written to job_skills. Counts
    # concepts, not spans: a posting naming Python four times resolves once.
    mentions_resolved: int = 0
    # Mentions recorded in job_skill_mentions because they resolved to no single
    # concept. Nothing matches against that table.
    mentions_unknown: int = 0
    # Postings whose skills could not be written. The posting itself is stored,
    # and this deliberately does not join `failures`: a failure there would make
    # the run neither processing-complete nor source-exhausted, and so would
    # block reconciliation from withdrawing a posting over an enrichment
    # problem that says nothing about whether the posting is gone.
    extraction_failed: int = 0

    @property
    def mentions_discarded(self) -> int:
        """Mentions the admission gate refused for matching.

        Equal to `mentions_unknown` while the gate decided in #190 stays closed,
        because refusing a candidate and recording it as an observation are the
        same act. Reported separately so that the day the gate opens, the two
        diverge in every run summary rather than silently.
        """
        return self.mentions_unknown

    @property
    def persisted(self) -> int:
        return self.created + self.updated

    @property
    def failed(self) -> int:
        return len(self.failures)

    @property
    def processing_complete(self) -> bool:
        """Whether every record this run fetched reached a persistence outcome.

        Says nothing about how much of the source was fetched. A run that read
        a tenth of a board and handled all of it is processing-complete.
        """
        return self.fetched == self.persisted + self.skipped and not self.failures

    @property
    def source_exhausted(self) -> bool:
        """Whether this run saw everything the source has.

        The stronger claim, and the only one that licenses concluding a posting
        is gone because it was not seen. Absence is evidence only when the
        alternative explanations are excluded, so every one of them is:

        - a run that stopped at its record budget did not look at the rest
        - a run that did not reach the end of the provider stopped early
        - a run with any failure, at any stage, has a record it cannot account
          for, and a posting it failed to read looks exactly like one that is
          gone

        A run may be processing-complete without being exhausted. The reverse
        cannot happen, because a failure denies both.
        """
        return self.reached_the_end and not self.stopped_at_budget and self.processing_complete


@runtime_checkable
class JobSourceClient(Protocol):
    """Fetches untrusted pages from one provider."""

    @property
    def source_key(self) -> str: ...

    @property
    def reached_the_end(self) -> bool:
        """Whether the last walk read everything the client was asked to read.

        False until `fetch_pages` has run out of pages of its own accord. A
        client that stopped at its own page limit, or skipped something it could
        not read, has not reached the end and must say so: the lifecycle rule
        treats an unseen posting as gone.
        """
        ...

    def fetch_pages(self) -> AsyncIterator[RawPage]:
        """Yield everything the provider has, within the client's own bound.

        How a provider is walked lives here rather than in the pipeline, because
        its shape is provider-specific. Page numbers, cursors, continuation
        tokens, and one request per company board all satisfy this boundary, and
        the run cannot tell them apart.

        A page number was once part of this contract. It was removed when a
        provider arrived that has no pages: the run never called it, so it only
        described how the first provider happened to work.
        """
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

    def normalize(self, record: ProviderRecordT, raw: RawRecord) -> NormalizedJob:
        """Return the canonical job, or raise `RecordValidationError`.

        The untrusted `raw` record is passed alongside the validated one so
        provenance can preserve exactly what the provider sent, including the
        fields validation ignored.
        """
        ...
