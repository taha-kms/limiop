import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete, func, select
from sqlalchemy import text as sql

from app.db.session import Database
from app.modules.ingestion import persistence
from app.modules.ingestion.contracts import IngestionStage, RecordOutcome
from app.modules.ingestion.persistence import (
    PersistenceResult,
    SourceRegistration,
    persist_job,
)
from app.modules.jobs.domain import EmploymentType, WorkplaceType
from app.modules.jobs.fingerprint import fingerprint, fingerprint_of
from app.modules.jobs.models import Company, Job, JobProvenance, JobSource
from app.modules.jobs.schemas import NormalizedJob

SOURCE = SourceRegistration(
    key="arbeitnow",
    display_name="Arbeitnow",
    base_url="https://www.arbeitnow.com/api/job-board-api",
)
FIRST_SEEN = datetime(2026, 8, 18, 10, tzinfo=UTC)
LATER_SEEN = datetime(2026, 8, 19, 10, tzinfo=UTC)


def incoming_job(**overrides: Any) -> NormalizedJob:
    payload: dict[str, Any] = {
        "company": {"display_name": "Acme GmbH"},
        "title": "Senior Data Engineer",
        "description": "Build reliable data pipelines.",
        "location": "Berlin",
        "workplace_type": "remote",
        "employment_type": "full-time",
        "application_url": "https://acme.example.com/jobs/data-engineer",
        "published_at": FIRST_SEEN,
        "provenance": {
            "source_key": "arbeitnow",
            "source_job_id": "external-42",
            "source_url": "https://arbeitnow.example.com/jobs/42",
            "raw_payload": {"slug": "external-42"},
        },
    }
    payload.update(overrides)
    return NormalizedJob.model_validate(payload)


async def divide_by_zero(session: Any, **_: Any) -> None:
    """Provoke a genuine PostgreSQL error from inside the record's savepoint."""
    await session.execute(sql("SELECT 1 / 0"))


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def clear(database: Database) -> None:
        async with database.session() as session:
            await session.execute(delete(JobProvenance))
            await session.execute(delete(Job))
            await session.execute(delete(Company))
            await session.execute(delete(JobSource))
            await session.commit()

    async def run() -> None:
        database = Database(database_url)
        try:
            await clear(database)
            await test(database)
        finally:
            await clear(database)
            await database.dispose()

    asyncio.run(run())


async def ingest(
    database: Database,
    incoming: NormalizedJob,
    *,
    seen_at: datetime = FIRST_SEEN,
) -> PersistenceResult:
    async with database.session() as session:
        result = await persist_job(session, incoming, source=SOURCE, seen_at=seen_at)
        await session.commit()
    return result


async def counts(database: Database) -> tuple[int, int, int, int]:
    async with database.session() as session:
        return (
            await session.scalar(select(func.count()).select_from(Job)) or 0,
            await session.scalar(select(func.count()).select_from(Company)) or 0,
            await session.scalar(select(func.count()).select_from(JobProvenance)) or 0,
            await session.scalar(select(func.count()).select_from(JobSource)) or 0,
        )


@pytest.mark.integration
def test_a_new_record_creates_the_job_company_source_and_provenance(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        result = await ingest(database, incoming_job())

        assert result.outcome is RecordOutcome.CREATED
        assert result.job_id is not None
        assert result.failure is None
        assert await counts(database) == (1, 1, 1, 1)

        async with database.session() as session:
            stored = (await session.scalars(select(Job))).one()

        assert stored.title == "Senior Data Engineer"
        assert stored.fingerprint == fingerprint(incoming_job())

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_reprocessing_the_same_record_changes_nothing(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        first = await ingest(database, incoming_job())
        second = await ingest(database, incoming_job(), seen_at=LATER_SEEN)
        third = await ingest(database, incoming_job(), seen_at=LATER_SEEN)

        assert first.outcome is RecordOutcome.CREATED
        assert second.outcome is RecordOutcome.SKIPPED
        assert third.outcome is RecordOutcome.SKIPPED
        assert second.job_id == first.job_id
        assert await counts(database) == (1, 1, 1, 1)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_reseeing_a_record_moves_only_the_last_seen_time(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, incoming_job())
        await ingest(database, incoming_job(), seen_at=LATER_SEEN)

        async with database.session() as session:
            provenance = (await session.scalars(select(JobProvenance))).one()

        assert provenance.first_seen_at == FIRST_SEEN
        assert provenance.last_seen_at == LATER_SEEN

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_changed_record_updates_the_existing_job(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        created = await ingest(database, incoming_job())
        updated = await ingest(
            database,
            incoming_job(description="Build reliable data pipelines. Now with Kafka."),
            seen_at=LATER_SEEN,
        )

        assert updated.outcome is RecordOutcome.UPDATED
        assert updated.job_id == created.job_id
        assert await counts(database) == (1, 1, 1, 1)

        async with database.session() as session:
            stored = (await session.scalars(select(Job))).one()

        assert stored.description.endswith("Now with Kafka.")

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_renamed_record_keeps_one_job_and_refreshes_the_fingerprint(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        created = await ingest(database, incoming_job())
        renamed = incoming_job(title="Staff Data Engineer")
        updated = await ingest(database, renamed, seen_at=LATER_SEEN)

        assert updated.outcome is RecordOutcome.UPDATED
        assert updated.job_id == created.job_id
        assert await counts(database) == (1, 1, 1, 1)

        async with database.session() as session:
            stored = (await session.scalars(select(Job))).one()

        assert stored.title == "Staff Data Engineer"
        assert stored.fingerprint == fingerprint(renamed)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_second_job_from_the_same_company_reuses_the_company(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, incoming_job())
        await ingest(
            database,
            incoming_job(
                title="Platform Engineer",
                company={"display_name": "ACME  gmbh"},
                provenance={
                    "source_key": "arbeitnow",
                    "source_job_id": "external-43",
                    "source_url": "https://arbeitnow.example.com/jobs/43",
                },
            ),
        )

        assert await counts(database) == (2, 1, 2, 1)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_source_is_registered_once(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, incoming_job())
        await ingest(
            database,
            incoming_job(
                title="Platform Engineer",
                provenance={
                    "source_key": "arbeitnow",
                    "source_job_id": "external-43",
                    "source_url": "https://arbeitnow.example.com/jobs/43",
                },
            ),
        )

        async with database.session() as session:
            source = (await session.scalars(select(JobSource))).one()

        assert source.key == "arbeitnow"
        assert source.base_url == SOURCE.base_url

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_record_from_another_source_is_refused(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        foreign = incoming_job(
            provenance={
                "source_key": "jobicy",
                "source_job_id": "98765",
                "source_url": "https://jobicy.example.com/jobs/98765",
            }
        )

        result = await ingest(database, foreign)

        assert result.outcome is RecordOutcome.SKIPPED
        assert result.failure is not None
        assert result.failure.stage is IngestionStage.PERSIST
        assert "jobicy" in result.failure.reason
        assert await counts(database) == (0, 0, 0, 0)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_ambiguous_match_is_reported_and_nothing_is_written(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        incoming = incoming_job()
        value = fingerprint(incoming)
        async with database.session() as session:
            company = Company(display_name="Acme GmbH")
            for index in range(2):
                session.add(
                    Job(
                        company=company,
                        fingerprint=value,
                        title=incoming.title,
                        description=f"Duplicate {index}",
                        application_url=str(incoming.application_url),
                    )
                )
            await session.commit()

        result = await ingest(database, incoming)

        assert result.outcome is RecordOutcome.SKIPPED
        assert result.job_id is None
        assert result.failure is not None
        assert "2 stored jobs" in result.failure.reason
        assert await counts(database) == (2, 1, 0, 0)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_write_failure_rolls_back_without_breaking_the_session(
    database_url: PostgresDsn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The canonical contract rejects unstorable values long before persistence,
    so a real database fault is injected mid-write instead."""

    async def exercise(database: Database) -> None:
        async with database.session() as session:
            monkeypatch.setattr(persistence, "observe_job_provenance", divide_by_zero)
            failed = await persist_job(session, incoming_job(), source=SOURCE, seen_at=FIRST_SEEN)

            monkeypatch.undo()
            recovered = await persist_job(
                session,
                incoming_job(),
                source=SOURCE,
                seen_at=FIRST_SEEN,
            )
            await session.commit()

        assert failed.outcome is RecordOutcome.SKIPPED
        assert failed.job_id is None
        assert failed.failure is not None
        assert failed.failure.stage is IngestionStage.PERSIST
        assert failed.failure.source_job_id == "external-42"
        assert recovered.outcome is RecordOutcome.CREATED
        assert await counts(database) == (1, 1, 1, 1)

        async with database.session() as session:
            stored = (await session.scalars(select(Job))).one()

        assert stored.title == "Senior Data Engineer"

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_partial_write_leaves_no_orphaned_rows(
    database_url: PostgresDsn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            monkeypatch.setattr(persistence, "observe_job_provenance", divide_by_zero)
            result = await persist_job(session, incoming_job(), source=SOURCE, seen_at=FIRST_SEEN)
            await session.commit()

        assert result.outcome is RecordOutcome.SKIPPED
        assert await counts(database) == (0, 0, 0, 0)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_failure_reason_never_repeats_provider_data(
    database_url: PostgresDsn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise(database: Database) -> None:
        secret = "candidate-only-internal-note"

        async with database.session() as session:
            monkeypatch.setattr(persistence, "observe_job_provenance", divide_by_zero)
            result = await persist_job(
                session,
                incoming_job(description=secret),
                source=SOURCE,
                seen_at=FIRST_SEEN,
            )
            await session.commit()

        assert result.failure is not None
        assert secret not in result.failure.reason
        assert result.failure.reason == "DataError while writing the record"

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_raw_payload_is_preserved_for_reproducing_transformations(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await ingest(database, incoming_job())

        async with database.session() as session:
            provenance = (await session.scalars(select(JobProvenance))).one()

        assert provenance.raw_payload == {"slug": "external-42"}

    run_database_test(database_url, exercise)


# Two sources describing one job. The aggregator ranks below the employer's own
# board, matching the ordering the second-source evaluation settled on.
#
# They agree on company, title, and location, because those three are the
# fingerprint inputs and a job is only recognised as the same job when they
# match. Disagreeing about them is a deduplication problem rather than an
# ownership one, and #95 owns it; the last test here pins that boundary so it
# is a known limit rather than a surprise.

AGGREGATOR = SourceRegistration(
    key="aggregator",
    display_name="Aggregator",
    base_url="https://aggregator.example.com",
    precedence=10,
)
BOARD = SourceRegistration(
    key="board",
    display_name="Employer board",
    base_url="https://board.example.com",
    precedence=20,
)


def from_source(source: SourceRegistration, **overrides: Any) -> NormalizedJob:
    """The same posting as one source describes it."""
    payload: dict[str, Any] = {
        "company": {"display_name": "Anthropic"},
        "title": "Enterprise Account Executive, Insurance",
        "description": "Sell things.",
        "location": "London",
        "workplace_type": "unspecified",
        "employment_type": "unspecified",
        "application_url": "https://anthropic.example.com/jobs/1",
        "provenance": {
            "source_key": source.key,
            "source_job_id": f"{source.key}-1",
            "source_url": f"{source.base_url}/jobs/1",
        },
    }
    payload.update(overrides)
    return NormalizedJob.model_validate(payload)


async def ingest_from(
    database: Database,
    source: SourceRegistration,
    incoming: NormalizedJob,
    *,
    seen_at: datetime = FIRST_SEEN,
) -> PersistenceResult:
    async with database.session() as session:
        result = await persist_job(session, incoming, source=source, seen_at=seen_at)
        await session.commit()
    return result


async def stored_job(database: Database) -> Job:
    async with database.session() as session:
        return (await session.scalars(select(Job))).one()


@pytest.mark.integration
def test_a_higher_ranked_source_owns_a_field_both_describe(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await ingest_from(database, AGGREGATOR, from_source(AGGREGATOR, description="Copied."))
        await ingest_from(
            database,
            BOARD,
            from_source(BOARD, description="Written by the employer."),
            seen_at=LATER_SEEN,
        )

        assert (await stored_job(database)).description == "Written by the employer."

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_lower_ranked_source_cannot_take_a_field_back(database_url: PostgresDsn) -> None:
    """The reason the rule exists: the runs alternate, the record must not."""

    async def exercise(database: Database) -> None:
        await ingest_from(database, BOARD, from_source(BOARD, workplace_type="onsite"))
        result = await ingest_from(
            database,
            AGGREGATOR,
            from_source(AGGREGATOR, workplace_type="remote"),
            seen_at=LATER_SEEN,
        )

        assert result.outcome is RecordOutcome.SKIPPED
        assert (await stored_job(database)).workplace_type is WorkplaceType.ONSITE

    run_database_test(database_url, exercise)


@pytest.mark.integration
@pytest.mark.parametrize("board_first", [True, False], ids=["board first", "aggregator first"])
def test_the_record_is_the_same_whichever_source_ran_last(
    database_url: PostgresDsn,
    board_first: bool,
) -> None:
    async def exercise(database: Database) -> None:
        board = from_source(BOARD, workplace_type="onsite", description="Employer copy.")
        aggregator = from_source(AGGREGATOR, workplace_type="remote", description="Copied.")
        order = [(BOARD, board), (AGGREGATOR, aggregator)]
        if not board_first:
            order.reverse()

        # Several rounds, because a rule that only settles after one pass would
        # still flip the record on every scheduled run.
        for _ in range(3):
            for source, incoming in order:
                await ingest_from(database, source, incoming, seen_at=LATER_SEEN)

        job = await stored_job(database)
        assert job.workplace_type is WorkplaceType.ONSITE
        assert job.description == "Employer copy."
        assert await counts(database) == (1, 1, 2, 2)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_silence_never_overwrites_something_another_source_said(
    database_url: PostgresDsn,
) -> None:
    """Nothing tells a dropped field apart from one a provider never carried."""

    async def exercise(database: Database) -> None:
        await ingest_from(
            database,
            BOARD,
            from_source(BOARD, workplace_type="onsite", employment_type="full-time"),
        )
        await ingest_from(
            database,
            AGGREGATOR,
            from_source(AGGREGATOR),
            seen_at=LATER_SEEN,
        )

        job = await stored_job(database)
        assert job.workplace_type is WorkplaceType.ONSITE
        assert job.employment_type is EmploymentType.FULL_TIME

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_lower_ranked_source_still_fills_a_field_nobody_had(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await ingest_from(database, BOARD, from_source(BOARD, workplace_type="onsite"))
        result = await ingest_from(
            database,
            AGGREGATOR,
            from_source(AGGREGATOR, workplace_type="remote", employment_type="internship"),
            seen_at=LATER_SEEN,
        )

        job = await stored_job(database)
        assert result.outcome is RecordOutcome.UPDATED
        assert job.employment_type is EmploymentType.INTERNSHIP
        assert job.workplace_type is WorkplaceType.ONSITE

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_lower_ranked_source_still_records_that_it_saw_the_job(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await ingest_from(database, BOARD, from_source(BOARD, workplace_type="onsite"))
        await ingest_from(database, AGGREGATOR, from_source(AGGREGATOR), seen_at=LATER_SEEN)

        async with database.session() as session:
            provenance = (await session.scalars(select(JobProvenance))).all()

        assert {p.source_job_id for p in provenance} == {"board-1", "aggregator-1"}
        assert await counts(database) == (1, 1, 2, 2)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_fingerprint_describes_what_is_stored_not_what_arrived(
    database_url: PostgresDsn,
) -> None:
    """A merged job holds values no single record carries, and must hash as itself."""

    async def exercise(database: Database) -> None:
        await ingest_from(database, BOARD, from_source(BOARD, title="Engineer"))
        await ingest_from(
            database,
            AGGREGATOR,
            from_source(AGGREGATOR, title="Engineer", description="Copied."),
            seen_at=LATER_SEEN,
        )

        job = await stored_job(database)
        assert job.fingerprint == fingerprint_of("Anthropic", "Engineer", "London")

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_one_source_can_still_correct_itself(database_url: PostgresDsn) -> None:
    """Equal rank goes to the incoming record, or a source could never fix a typo."""

    async def exercise(database: Database) -> None:
        await ingest_from(database, BOARD, from_source(BOARD, description="Sel things."))
        result = await ingest_from(
            database,
            BOARD,
            from_source(BOARD, description="Sell things."),
            seen_at=LATER_SEEN,
        )

        assert result.outcome is RecordOutcome.UPDATED
        assert (await stored_job(database)).description == "Sell things."

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_ranking_change_reaches_records_written_after_it(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await ingest_from(database, AGGREGATOR, from_source(AGGREGATOR, description="First."))
        promoted = SourceRegistration(
            key=AGGREGATOR.key,
            display_name=AGGREGATOR.display_name,
            base_url=AGGREGATOR.base_url,
            precedence=99,
        )

        async with database.session() as session:
            await persist_job(
                session,
                from_source(AGGREGATOR, description="Second."),
                source=promoted,
                seen_at=LATER_SEEN,
            )
            await session.commit()
            assert (await session.scalars(select(JobSource))).one().precedence == 99

        assert (await stored_job(database)).description == "Second."

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_disagreeing_about_a_fingerprint_field_still_stores_two_jobs(
    database_url: PostgresDsn,
) -> None:
    """The boundary of this rule, pinned so it is a known limit and not a surprise.

    Ownership only applies once two records are recognised as the same job, and
    recognition runs on company, title, and location. Sources that describe the
    location differently never reach the merge at all. #95 owns that.
    """

    async def exercise(database: Database) -> None:
        await ingest_from(database, BOARD, from_source(BOARD, location="London, UK"))
        await ingest_from(
            database,
            AGGREGATOR,
            from_source(AGGREGATOR, location="London"),
            seen_at=LATER_SEEN,
        )

        jobs, *_ = await counts(database)
        assert jobs == 2

    run_database_test(database_url, exercise)
