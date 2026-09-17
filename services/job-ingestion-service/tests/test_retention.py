"""Catalogue retention: what leaves the catalogue once it stopped being listable.

Every test here writes real rows, because the rule is about what a delete takes
with it and what a foreign key refuses, and neither is visible without the
schema.
"""

import asyncio
from collections.abc import Awaitable, Callable, Collection
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from platform_db.models import Company, Job, JobProvenance, JobSource
from platform_db.models.catalog import JobStatus
from platform_db.models.job_skills import JobSkill, JobSkillMention
from platform_db.models.skills import SkillAliasVersion, SkillConcept
from pydantic import PostgresDsn
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.config import Environment, Settings
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration, persist_job
from job_ingestion.reconciliation import expire_jobs_past_their_stated_date
from job_ingestion.retention import (
    ANONYMISED_AT_KEY,
    ANONYMISED_DESCRIPTION,
    ReferenceProbe,
    RetentionPolicy,
    RetentionResult,
    apply_retention,
    run_retention,
)
from job_ingestion.schemas import NormalizedJob
from tests.support.catalog import with_empty_catalog

NOW = datetime(2026, 9, 17, 3, 15, tzinfo=UTC)
GRACE = timedelta(days=30)
BEFORE_THE_GRACE = NOW - GRACE - timedelta(days=1)
WITHIN_THE_GRACE = NOW - GRACE + timedelta(days=1)

VERSION = "2026.09.17.1"
PYTHON = UUID("11111111-1111-4111-8111-111111111111")
SOURCE_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_SOURCE_ID = UUID("44444444-4444-4444-8444-444444444444")
PAYLOAD: dict[str, object] = {"id": "board-1", "title": "Senior Data Engineer"}


async def clear_vocabulary(database: Database) -> None:
    """Drop the alias table the skill rows point at. Only valid on an empty catalog."""
    async with database.session() as session:
        await session.execute(delete(SkillConcept))
        await session.execute(delete(SkillAliasVersion))
        await session.commit()


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def seeded(database: Database) -> None:
        await clear_vocabulary(database)
        async with database.session() as session:
            session.add(SkillAliasVersion(version=VERSION))
            session.add(SkillConcept(id=PYTHON, preferred_label="Python"))
            session.add_all(
                JobSource(
                    id=source_id, key=key, display_name=key, base_url=f"https://{key}.example.com"
                )
                for source_id, key in ((SOURCE_ID, "board"), (OTHER_SOURCE_ID, "aggregator"))
            )
            await session.commit()
        await test(database)

    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, seeded)
        finally:
            # The catalog is empty again by now, so nothing references the
            # alias table any more.
            await clear_vocabulary(database)
            await database.dispose()

    asyncio.run(run())


async def store_job(
    database: Database,
    *,
    status: JobStatus,
    updated_at: datetime,
    expires_at: datetime | None = None,
) -> UUID:
    """A job with one provenance row, one skill and one mention, as ingestion leaves it."""
    job_id = uuid4()
    async with database.session() as session:
        company = Company(display_name="Acme GmbH")
        session.add(company)
        await session.flush()
        session.add(
            Job(
                id=job_id,
                company_id=company.id,
                title="Senior Data Engineer",
                description="Build the pipelines the analytics team depends on.",
                location="Berlin",
                application_url="https://acme.example.com/jobs/1",
                published_at=BEFORE_THE_GRACE - timedelta(days=60),
                expires_at=expires_at,
                status=status,
                updated_at=updated_at,
            )
        )
        await session.flush()
        session.add(
            JobProvenance(
                job_id=job_id,
                source_id=SOURCE_ID,
                source_job_id=str(job_id),
                source_url=f"https://board.example.com/jobs/{job_id}",
                raw_payload=dict(PAYLOAD),
                # The source stopped listing it when the job stopped being active.
                retired_at=None if status is JobStatus.ACTIVE else updated_at,
            )
        )
        session.add(
            JobSkill(
                job_id=job_id,
                concept_id=PYTHON,
                alias_version=VERSION,
                surface_form="Python",
            )
        )
        session.add(
            JobSkillMention(
                job_id=job_id,
                surface_form="Airflow",
                normalized_form="airflow",
                occurrences=1,
                first_seen_at=updated_at,
                last_seen_at=updated_at,
                extractor_version="test",
                alias_version=VERSION,
            )
        )
        await session.commit()
    return job_id


async def rows_of(database: Database, job_id: UUID) -> dict[str, int]:
    """How many rows of each kind still name the job."""
    async with database.session() as session:
        counts = {}
        for name, column in (
            ("jobs", Job.id),
            ("provenance", JobProvenance.job_id),
            ("skills", JobSkill.job_id),
            ("mentions", JobSkillMention.job_id),
        ):
            counts[name] = (
                await session.execute(
                    select(func.count()).select_from(column.class_).where(column == job_id)
                )
            ).scalar_one()
        return counts


INTACT = {"jobs": 1, "provenance": 1, "skills": 1, "mentions": 1}
GONE = {"jobs": 0, "provenance": 0, "skills": 0, "mentions": 0}
DEFAULT_POLICY = RetentionPolicy()


async def retain(
    database: Database,
    *,
    policy: RetentionPolicy = DEFAULT_POLICY,
    now: datetime = NOW,
) -> RetentionResult:
    async with database.session() as session:
        result = await apply_retention(session, now=now, policy=policy)
        await session.commit()
    return result


def test_the_default_grace_is_thirty_days() -> None:
    assert RetentionPolicy().grace == timedelta(days=30)


@pytest.mark.integration
def test_a_withdrawn_job_past_the_grace_leaves_with_everything_it_owned(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)

        result = await retain(database)

        assert result == RetentionResult(deleted=1, anonymised=0, examined=1)
        assert await rows_of(database, job_id) == GONE

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_withdrawn_job_inside_the_grace_is_untouched(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(database, status=JobStatus.REMOVED, updated_at=WITHIN_THE_GRACE)

        result = await retain(database)

        assert result == RetentionResult(deleted=0, anonymised=0, examined=0)
        assert await rows_of(database, job_id) == INTACT

    run_database_test(database_url, test)


@pytest.mark.integration
def test_an_expired_job_past_the_grace_is_deleted(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(
            database,
            status=JobStatus.EXPIRED,
            updated_at=BEFORE_THE_GRACE,
            expires_at=BEFORE_THE_GRACE,
        )

        result = await retain(database)

        assert result == RetentionResult(deleted=1, anonymised=0, examined=1)
        assert await rows_of(database, job_id) == GONE

    run_database_test(database_url, test)


@pytest.mark.integration
def test_an_active_job_is_never_touched_however_old(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(
            database,
            status=JobStatus.ACTIVE,
            updated_at=NOW - timedelta(days=3650),
        )

        result = await retain(database)

        assert result == RetentionResult(deleted=0, anonymised=0, examined=0)
        assert await rows_of(database, job_id) == INTACT

    run_database_test(database_url, test)


@pytest.mark.integration
def test_the_grace_period_is_the_policy_s_to_set(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(database, status=JobStatus.REMOVED, updated_at=WITHIN_THE_GRACE)

        result = await retain(database, policy=RetentionPolicy(grace=timedelta(days=7)))

        assert result.deleted == 1
        assert await rows_of(database, job_id) == GONE

    run_database_test(database_url, test)


@pytest.mark.integration
def test_the_result_counts_what_one_pass_examined(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        withdrawn = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)
        expired = await store_job(
            database,
            status=JobStatus.EXPIRED,
            updated_at=BEFORE_THE_GRACE,
            expires_at=BEFORE_THE_GRACE,
        )
        recent = await store_job(database, status=JobStatus.REMOVED, updated_at=WITHIN_THE_GRACE)
        active = await store_job(database, status=JobStatus.ACTIVE, updated_at=BEFORE_THE_GRACE)

        result = await retain(database)

        assert result == RetentionResult(deleted=2, anonymised=0, examined=2)
        assert await rows_of(database, withdrawn) == GONE
        assert await rows_of(database, expired) == GONE
        assert await rows_of(database, recent) == INTACT
        assert await rows_of(database, active) == INTACT

    run_database_test(database_url, test)


# The candidate clock is `jobs.updated_at`. That only works because a status
# flip moves it, which the model promises through `onupdate` and this proves.


@pytest.mark.integration
def test_a_status_flip_restarts_the_clock(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(
            database,
            status=JobStatus.ACTIVE,
            updated_at=BEFORE_THE_GRACE,
            expires_at=WITHIN_THE_GRACE,
        )

        async with database.session() as session:
            await expire_jobs_past_their_stated_date(session, now=NOW)
            await session.commit()

        result = await retain(database)

        assert result == RetentionResult(deleted=0, anonymised=0, examined=0)
        assert await rows_of(database, job_id) == INTACT
        async with database.session() as session:
            job = await session.get_one(Job, job_id)
            assert job.status is JobStatus.EXPIRED
            assert job.updated_at > BEFORE_THE_GRACE

    run_database_test(database_url, test)


# The schema has no user-facing table that points at a job yet, so a reference
# is whatever the policy says one is. This one says the job it is handed.


def referencing(job_id: UUID) -> ReferenceProbe:
    async def probe(_session: AsyncSession, candidates: Collection[UUID]) -> set[UUID]:
        return {job_id} & set(candidates)

    return probe


async def job_row(database: Database, job_id: UUID) -> Job:
    async with database.session() as session:
        return await session.get_one(Job, job_id)


async def payloads_of(database: Database, job_id: UUID) -> list[dict[str, object] | None]:
    async with database.session() as session:
        rows = await session.scalars(
            select(JobProvenance.raw_payload).where(JobProvenance.job_id == job_id)
        )
        return list(rows)


@pytest.mark.integration
def test_a_referenced_job_is_anonymised_rather_than_deleted(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)
        before = await job_row(database, job_id)

        result = await retain(database, policy=RetentionPolicy(references=(referencing(job_id),)))

        assert result == RetentionResult(deleted=0, anonymised=1, examined=1)
        assert await rows_of(database, job_id) == INTACT
        assert await payloads_of(database, job_id) == [{ANONYMISED_AT_KEY: NOW.isoformat()}]
        after = await job_row(database, job_id)
        assert after.description == ANONYMISED_DESCRIPTION
        assert after.location is None
        assert after.application_url == ""
        assert after.company_id == before.company_id
        assert after.status is JobStatus.REMOVED
        assert after.title == before.title
        assert after.anonymised_at == NOW

    run_database_test(database_url, test)


@pytest.mark.integration
def test_an_anonymised_job_is_not_a_candidate_again(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)
        policy = RetentionPolicy(references=(referencing(job_id),))
        await retain(database, policy=policy)
        first = await job_row(database, job_id)

        # Long after the anonymisation itself has aged out of the grace, and
        # with nothing referencing the job any more.
        later = NOW + GRACE + timedelta(days=365)
        result = await retain(database, now=later)

        assert result == RetentionResult(deleted=0, anonymised=0, examined=0)
        assert await rows_of(database, job_id) == INTACT
        assert await payloads_of(database, job_id) == [{ANONYMISED_AT_KEY: NOW.isoformat()}]
        assert (await job_row(database, job_id)).updated_at == first.updated_at

    run_database_test(database_url, test)


@pytest.mark.integration
def test_references_from_every_probe_count(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        kept = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)
        also_kept = await store_job(database, status=JobStatus.EXPIRED, updated_at=BEFORE_THE_GRACE)
        gone = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)
        policy = RetentionPolicy(references=(referencing(kept), referencing(also_kept)))

        result = await retain(database, policy=policy)

        assert result == RetentionResult(deleted=1, anonymised=2, examined=3)
        assert await rows_of(database, kept) == INTACT
        assert await rows_of(database, also_kept) == INTACT
        assert await rows_of(database, gone) == GONE

    run_database_test(database_url, test)


@pytest.mark.integration
def test_the_entry_point_opens_the_configured_database_and_commits(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(
            database,
            status=JobStatus.REMOVED,
            updated_at=datetime.now(UTC) - GRACE - timedelta(days=1),
        )
        settings = Settings(environment=Environment.TEST, database_url=database_url)

        result = await run_retention(settings=settings)

        assert result == RetentionResult(deleted=1, anonymised=0, examined=1)
        assert await rows_of(database, job_id) == GONE

    run_database_test(database_url, test)


# Paging. Every page is selected under a row lock, committed on its own, and
# the statements that finally act restate the whole predicate.


def test_a_page_holds_at_least_one_job() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        RetentionPolicy(batch_size=0)


async def store_withdrawn_jobs(database: Database, count: int) -> None:
    """Withdrawn jobs past the grace, with nothing hanging off them, in one write."""
    async with database.session() as session:
        company = Company(display_name="Acme GmbH")
        session.add(company)
        await session.flush()
        session.add_all(
            Job(
                company_id=company.id,
                title=f"Engineer {index}",
                description="Gone.",
                application_url=f"https://acme.example.com/jobs/{index}",
                status=JobStatus.REMOVED,
                updated_at=BEFORE_THE_GRACE - timedelta(minutes=index),
            )
            for index in range(count)
        )
        await session.commit()


async def count_jobs(database: Database) -> int:
    async with database.session() as session:
        return (await session.execute(select(func.count()).select_from(Job))).scalar_one()


@pytest.mark.integration
def test_a_large_backlog_is_removed_page_by_page_with_a_commit_per_page(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        await store_withdrawn_jobs(database, 1200)
        pages: list[int] = []

        async def counting(_session: AsyncSession, candidates: Collection[UUID]) -> set[UUID]:
            pages.append(len(candidates))
            return set()

        policy = RetentionPolicy(references=(counting,), batch_size=500)
        async with database.session() as session:
            with patch.object(session, "commit", AsyncMock(wraps=session.commit)) as commit:
                result = await apply_retention(session, now=NOW, policy=policy)

        assert result == RetentionResult(deleted=1200, anonymised=0, examined=1200)
        assert pages == [500, 500, 200]
        assert commit.await_count == 3
        assert await count_jobs(database) == 0

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_job_another_session_is_writing_is_left_to_that_session(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)

        # An ingestion run mid-write holds the row; it is about to re-list the job.
        async with database.session() as writer:
            await writer.execute(select(Job.id).where(Job.id == job_id).with_for_update())

            result = await retain(database)

            await writer.execute(
                update(Job).where(Job.id == job_id).values(status=JobStatus.ACTIVE)
            )
            await writer.commit()

        assert result == RetentionResult(deleted=0, anonymised=0, examined=0)
        assert await rows_of(database, job_id) == INTACT
        assert (await job_row(database, job_id)).status is JobStatus.ACTIVE

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_job_whose_clock_moved_after_selection_is_not_deleted(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)

        # Something lands on the job between its selection and the delete: the
        # statements that act must notice, not trust the page they were given.
        async def relisting(session: AsyncSession, candidates: Collection[UUID]) -> set[UUID]:
            await session.execute(
                update(Job)
                .where(Job.id.in_(candidates))
                .values(status=JobStatus.ACTIVE, updated_at=NOW)
            )
            return set()

        result = await retain(database, policy=RetentionPolicy(references=(relisting,)))

        assert result == RetentionResult(deleted=0, anonymised=0, examined=1)
        assert await rows_of(database, job_id) == INTACT

    run_database_test(database_url, test)


# The marker is a fact about the job and lives on the job. Nothing here clears
# it: a source re-listing an anonymised job is issue #392.


async def add_provenance(database: Database, job_id: UUID, source_id: UUID) -> None:
    async with database.session() as session:
        session.add(
            JobProvenance(
                job_id=job_id,
                source_id=source_id,
                source_job_id=f"{source_id}-{job_id}",
                source_url=f"https://example.com/{job_id}",
                raw_payload=dict(PAYLOAD),
                retired_at=BEFORE_THE_GRACE,
            )
        )
        await session.commit()


async def relist(database: Database, job_id: UUID, source: SourceRegistration) -> None:
    """One source lists the posting again, exactly as ingestion would write it."""
    async with database.session() as session:
        job = await session.get_one(Job, job_id)
        company = await session.get_one(Company, job.company_id)
        record = await session.scalar(
            select(JobProvenance).where(
                JobProvenance.job_id == job_id, JobProvenance.source_id == SOURCE_ID
            )
        )
        assert record is not None
        incoming = NormalizedJob.model_validate(
            {
                "company": {"display_name": company.display_name},
                "title": job.title,
                "description": "Build the pipelines the analytics team depends on.",
                "location": "Berlin",
                "application_url": "https://acme.example.com/jobs/1",
                "provenance": {
                    "source_key": source.key,
                    "source_job_id": record.source_job_id,
                    "source_url": record.source_url,
                },
            }
        )
        outcome = await persist_job(session, incoming, source=source, seen_at=NOW)
        assert outcome.failure is None, outcome.failure
        await session.commit()


async def withdraw(database: Database, job_id: UUID, *, at: datetime) -> None:
    async with database.session() as session:
        await session.execute(
            update(JobProvenance).where(JobProvenance.job_id == job_id).values(retired_at=at)
        )
        await session.execute(
            update(Job).where(Job.id == job_id).values(status=JobStatus.REMOVED, updated_at=at)
        )
        await session.commit()


BOARD = SourceRegistration(key="board", display_name="Board", base_url="https://board.example.com")


@pytest.mark.integration
def test_a_partial_relist_does_not_unmark_an_anonymised_job(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)
        await add_provenance(database, job_id, OTHER_SOURCE_ID)
        await retain(database, policy=RetentionPolicy(references=(referencing(job_id),)))

        await relist(database, job_id, BOARD)
        assert (await job_row(database, job_id)).status is JobStatus.ACTIVE
        withdrawn_again = NOW + timedelta(days=10)
        await withdraw(database, job_id, at=withdrawn_again)

        result = await retain(database, now=withdrawn_again + GRACE + timedelta(days=1))

        assert result == RetentionResult(deleted=0, anonymised=0, examined=0)
        after = await job_row(database, job_id)
        assert after.anonymised_at == NOW
        assert after.status is JobStatus.REMOVED
        assert await rows_of(database, job_id) == {**INTACT, "provenance": 2}

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_job_with_no_provenance_is_marked_once(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        await store_withdrawn_jobs(database, 1)
        async with database.session() as session:
            job_id = (await session.execute(select(Job.id))).scalar_one()
        policy = RetentionPolicy(references=(referencing(job_id),))

        first = await retain(database, policy=policy)
        again = await retain(database, policy=policy, now=NOW + GRACE + timedelta(days=365))

        assert first == RetentionResult(deleted=0, anonymised=1, examined=1)
        assert again == RetentionResult(deleted=0, anonymised=0, examined=0)
        assert (await job_row(database, job_id)).anonymised_at == NOW

    run_database_test(database_url, test)


# A source that still lists the job has not stopped listing it, whatever the
# status says. Its provenance rows are locked with the page, so a source that
# re-lists mid-page either waits for the page or keeps the page off the job.


async def relist_provenance(database: Database, job_id: UUID) -> None:
    async with database.session() as session:
        await session.execute(
            update(JobProvenance).where(JobProvenance.job_id == job_id).values(retired_at=None)
        )
        await session.commit()


@pytest.mark.integration
def test_an_expired_job_a_source_still_lists_is_untouched(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(
            database,
            status=JobStatus.EXPIRED,
            updated_at=BEFORE_THE_GRACE,
            expires_at=BEFORE_THE_GRACE,
        )
        await relist_provenance(database, job_id)

        result = await retain(database)

        assert result == RetentionResult(deleted=0, anonymised=0, examined=0)
        assert await rows_of(database, job_id) == INTACT

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_source_relisting_mid_page_waits_for_the_page(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)
        relisting: dict[str, asyncio.Task[None]] = {}

        async def while_locked(_session: AsyncSession, _ids: Collection[UUID]) -> set[UUID]:
            relisting["task"] = asyncio.create_task(relist_provenance(database, job_id))
            await asyncio.sleep(0.3)
            assert not relisting["task"].done(), "the re-list should wait for the page"
            return set()

        result = await retain(database, policy=RetentionPolicy(references=(while_locked,)))
        await relisting["task"]

        assert result == RetentionResult(deleted=1, anonymised=0, examined=1)
        assert await rows_of(database, job_id) == GONE

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_job_whose_provenance_another_session_holds_is_skipped(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        job_id = await store_job(database, status=JobStatus.REMOVED, updated_at=BEFORE_THE_GRACE)

        async with database.session() as writer:
            await writer.execute(
                update(JobProvenance).where(JobProvenance.job_id == job_id).values(retired_at=None)
            )

            result = await retain(database)

            await writer.commit()

        assert result == RetentionResult(deleted=0, anonymised=0, examined=0)
        assert await rows_of(database, job_id) == INTACT

    run_database_test(database_url, test)
