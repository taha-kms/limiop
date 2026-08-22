"""One reusable entry point for running a provider's ingestion.

The run is provider-agnostic: it takes the three stage protocols from
`contracts` plus the identity to write under. A new provider needs a client, a
validator, and a normalizer, not new orchestration.

Nothing here knows about schedulers or HTTP routes, so the same call works from
an Airflow task, a management command, or a test.

Failure handling follows the split the contracts define. A record that cannot be
validated, normalized, or written is counted as a failure and the run continues.
A provider that cannot be reached ends the run, and everything already processed
is reported rather than discarded.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Database
from app.modules.ingestion.contracts import (
    IngestionStage,
    IngestionSummary,
    JobRecordNormalizer,
    JobRecordValidator,
    JobSourceClient,
    RawRecord,
    RecordFailure,
    RecordOutcome,
)
from app.modules.ingestion.errors import IngestionError, RecordValidationError
from app.modules.ingestion.persistence import SourceRegistration, persist_job
from app.modules.jobs.schemas import NormalizedJob

DEFAULT_MAX_RECORDS = 1000


class StageRejection(Exception):
    """Carries which stage rejected a record, alongside why."""

    def __init__(self, stage: IngestionStage, error: RecordValidationError) -> None:
        super().__init__(error.message)
        self.stage = stage
        self.error = error

    def as_failure(self) -> RecordFailure:
        return RecordFailure(
            stage=self.stage,
            reason=self.error.message,
            source_job_id=self.error.source_job_id,
        )


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class RunTally:
    """Running counts for one execution."""

    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0

    def record(self, outcome: RecordOutcome) -> None:
        if outcome is RecordOutcome.CREATED:
            self.created += 1
        elif outcome is RecordOutcome.UPDATED:
            self.updated += 1
        else:
            self.skipped += 1


@dataclass(frozen=True, slots=True)
class IngestionRun[ProviderRecordT]:
    """A configured, bounded ingestion for one provider."""

    client: JobSourceClient
    validator: JobRecordValidator[ProviderRecordT]
    normalizer: JobRecordNormalizer[ProviderRecordT]
    source: SourceRegistration
    max_records: int = DEFAULT_MAX_RECORDS

    def __post_init__(self) -> None:
        if self.max_records < 1:
            raise ValueError("max_records must be at least 1")

    def prepare(self, raw: RawRecord) -> NormalizedJob:
        """Validate then normalize one untrusted record.

        Both stages raise the same failure type, so they are attempted
        separately: a run must be able to say which one rejected the record.
        """
        try:
            record = self.validator.validate(raw)
        except RecordValidationError as error:
            raise StageRejection(IngestionStage.VALIDATE, error) from error

        try:
            return self.normalizer.normalize(record, raw)
        except RecordValidationError as error:
            raise StageRejection(IngestionStage.NORMALIZE, error) from error

    async def execute(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> IngestionSummary:
        """Run every stage in order and report what happened.

        Each record commits on its own, so a run interrupted halfway leaves the
        records it already handled durably stored.
        """
        tally = RunTally()
        failures: list[RecordFailure] = []
        stopped_at_budget = False

        async with database.session() as session:
            try:
                async for page in self.client.fetch_pages():
                    for raw in page.records:
                        if tally.fetched >= self.max_records:
                            # The rest of the source is unread, which is a
                            # different thing from there being no rest.
                            stopped_at_budget = True
                            return self.summarize(tally, failures, stopped_at_budget=True)
                        tally.fetched += 1
                        await self.handle(session, raw, tally, failures, clock())
            except IngestionError as error:
                failures.append(RecordFailure(stage=IngestionStage.FETCH, reason=error.message))

        return self.summarize(tally, failures, stopped_at_budget=stopped_at_budget)

    async def handle(
        self,
        session: AsyncSession,
        raw: RawRecord,
        tally: RunTally,
        failures: list[RecordFailure],
        seen_at: datetime,
    ) -> None:
        """Take one untrusted record as far as it can go."""
        try:
            normalized = self.prepare(raw)
        except StageRejection as rejection:
            failures.append(rejection.as_failure())
            return

        result = await persist_job(session, normalized, source=self.source, seen_at=seen_at)
        tally.record(result.outcome)
        if result.failure is not None:
            failures.append(result.failure)
        await session.commit()

    def summarize(
        self,
        tally: RunTally,
        failures: list[RecordFailure],
        *,
        stopped_at_budget: bool,
    ) -> IngestionSummary:
        return IngestionSummary(
            source_key=self.source.key,
            fetched=tally.fetched,
            created=tally.created,
            updated=tally.updated,
            skipped=tally.skipped,
            failures=tuple(failures),
            # Asked of the client rather than assumed: only it knows whether it
            # ran out of pages or out of allowance.
            reached_the_end=self.client.reached_the_end,
            stopped_at_budget=stopped_at_budget,
        )
