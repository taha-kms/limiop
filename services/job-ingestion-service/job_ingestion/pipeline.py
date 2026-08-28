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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.contracts import (
    IngestionStage,
    IngestionSummary,
    JobRecordNormalizer,
    JobRecordValidator,
    JobSourceClient,
    RawRecord,
    RecordFailure,
    RecordOutcome,
)
from job_ingestion.database import Database
from job_ingestion.errors import IngestionError, RecordValidationError
from job_ingestion.persistence import SourceRegistration, persist_job
from job_ingestion.schemas import NormalizedJob
from job_ingestion.skills import (
    ExtractionCounts,
    SkillVocabulary,
    load_skill_vocabulary,
    store_job_skills,
)

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
    extraction: ExtractionCounts = field(default_factory=ExtractionCounts)
    extraction_failed: int = 0

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
    skill_alias_version: str | None = None

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
            # Read once per run rather than per record: a publication landing
            # mid-run would otherwise split one run across two vocabularies and
            # make its own counts unreadable. A vocabulary that cannot be read
            # is no vocabulary: the run stores postings without skills rather
            # than not running at all.
            try:
                vocabulary = await load_skill_vocabulary(session, version=self.skill_alias_version)
            except Exception:
                vocabulary = None
            try:
                async for page in self.client.fetch_pages():
                    for raw in page.records:
                        if tally.fetched >= self.max_records:
                            # The rest of the source is unread, which is a
                            # different thing from there being no rest.
                            stopped_at_budget = True
                            return self.summarize(
                                tally, failures, stopped_at_budget=True, vocabulary=vocabulary
                            )
                        tally.fetched += 1
                        await self.handle(
                            session, raw, tally, failures, clock(), vocabulary=vocabulary
                        )
            except IngestionError as error:
                failures.append(RecordFailure(stage=IngestionStage.FETCH, reason=error.message))

        return self.summarize(
            tally, failures, stopped_at_budget=stopped_at_budget, vocabulary=vocabulary
        )

    async def handle(
        self,
        session: AsyncSession,
        raw: RawRecord,
        tally: RunTally,
        failures: list[RecordFailure],
        seen_at: datetime,
        *,
        vocabulary: SkillVocabulary | None = None,
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
        # A stored job, whatever the outcome. An unchanged posting is skipped
        # and still has a row, and it must keep its skills.
        if vocabulary is not None and result.job_id is not None:
            await self.enrich(
                session, tally, job_id=result.job_id, vocabulary=vocabulary, seen_at=seen_at
            )
        await session.commit()

    async def enrich(
        self,
        session: AsyncSession,
        tally: RunTally,
        *,
        job_id: UUID,
        vocabulary: SkillVocabulary,
        seen_at: datetime,
    ) -> None:
        """Attach skills to a job that is stored but not yet committed.

        Two layers, and both are needed. The savepoint keeps a failed skill
        write from poisoning the transaction the job is sitting in, because in
        PostgreSQL one failed statement aborts everything after it. The except
        keeps the exception from escaping to `Database.session`, which rolls the
        whole session back and would discard the job this run just wrote.

        The catch is broad on purpose. A database error is not the only way this
        fails: a vocabulary whose spellings collide after normalization makes
        the extractor raise, and that would otherwise end the run on its first
        record. Skills are enrichment, and no failure here is the posting's.
        """
        try:
            async with session.begin_nested():
                counts = await store_job_skills(
                    session,
                    job_id=job_id,
                    vocabulary=vocabulary,
                    seen_at=seen_at,
                )
        except Exception:
            tally.extraction_failed += 1
            return

        tally.extraction = tally.extraction + counts

    def summarize(
        self,
        tally: RunTally,
        failures: list[RecordFailure],
        *,
        stopped_at_budget: bool,
        vocabulary: SkillVocabulary | None = None,
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
            alias_version=vocabulary.version if vocabulary is not None else None,
            mentions_resolved=tally.extraction.resolved,
            mentions_unknown=tally.extraction.unknown,
            extraction_failed=tally.extraction_failed,
        )
