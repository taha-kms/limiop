import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete

from app.db.session import Database
from app.modules.ingestion.deduplication import (
    DeduplicationOutcome,
    MatchBasis,
    decide,
    has_material_change,
)
from app.modules.jobs.fingerprint import fingerprint
from app.modules.jobs.models import Company, Job, JobProvenance, JobSource
from app.modules.jobs.schemas import NormalizedJob

SOURCE_KEY = "arbeitnow"
PUBLISHED_AT = datetime(2026, 8, 18, 10, tzinfo=UTC)


def incoming_job(**overrides: Any) -> NormalizedJob:
    payload: dict[str, Any] = {
        "company": {"display_name": "Acme GmbH"},
        "title": "Senior Data Engineer",
        "description": "Build reliable data pipelines.",
        "location": "Berlin",
        "workplace_type": "remote",
        "employment_type": "full-time",
        "application_url": "https://acme.example.com/jobs/data-engineer",
        "published_at": PUBLISHED_AT,
        "provenance": {
            "source_key": SOURCE_KEY,
            "source_job_id": "external-42",
            "source_url": "https://arbeitnow.example.com/jobs/42",
        },
    }
    payload.update(overrides)
    return NormalizedJob.model_validate(payload)


def stored_job(incoming: NormalizedJob) -> Job:
    return Job(
        company=Company(display_name=incoming.company.display_name),
        fingerprint=fingerprint(incoming),
        title=incoming.title,
        description=incoming.description,
        location=incoming.location,
        workplace_type=incoming.workplace_type,
        employment_type=incoming.employment_type,
        application_url=str(incoming.application_url),
        published_at=incoming.published_at,
        expires_at=incoming.expires_at,
    )


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


async def store(database: Database, *rows: object) -> None:
    async with database.session() as session:
        session.add_all(list(rows))
        await session.commit()


@pytest.mark.integration
def test_an_unseen_job_is_new(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            decision = await decide(session, incoming_job())

        assert decision.outcome is DeduplicationOutcome.NEW
        assert decision.job_id is None
        assert decision.matched_by is None
        assert decision.fingerprint == fingerprint(incoming_job())

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_repeated_source_record_is_recognized(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        incoming = incoming_job()
        job = stored_job(incoming)
        source = JobSource(key=SOURCE_KEY, display_name="Arbeitnow", base_url="https://a.example")
        await store(
            database,
            JobProvenance(
                job=job,
                source=source,
                source_job_id=incoming.provenance.source_job_id,
                source_url=str(incoming.provenance.source_url),
            ),
        )

        async with database.session() as session:
            decision = await decide(session, incoming)

        assert decision.outcome is DeduplicationOutcome.UNCHANGED
        assert decision.matched_by is MatchBasis.PROVENANCE
        assert decision.job_id == job.id

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_changed_source_record_points_at_the_job_to_update(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        original = incoming_job()
        job = stored_job(original)
        source = JobSource(key=SOURCE_KEY, display_name="Arbeitnow", base_url="https://a.example")
        await store(
            database,
            JobProvenance(
                job=job,
                source=source,
                source_job_id=original.provenance.source_job_id,
                source_url=str(original.provenance.source_url),
            ),
        )
        updated = incoming_job(description="Build reliable data pipelines. Now with Kafka.")

        async with database.session() as session:
            decision = await decide(session, updated)

        assert decision.outcome is DeduplicationOutcome.CHANGED
        assert decision.matched_by is MatchBasis.PROVENANCE
        assert decision.job_id == job.id

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_provenance_wins_even_when_the_job_was_renamed(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        original = incoming_job()
        job = stored_job(original)
        source = JobSource(key=SOURCE_KEY, display_name="Arbeitnow", base_url="https://a.example")
        await store(
            database,
            JobProvenance(
                job=job,
                source=source,
                source_job_id=original.provenance.source_job_id,
                source_url=str(original.provenance.source_url),
            ),
        )
        renamed = incoming_job(title="Staff Data Engineer")

        async with database.session() as session:
            decision = await decide(session, renamed)

        assert decision.fingerprint != fingerprint(original)
        assert decision.outcome is DeduplicationOutcome.CHANGED
        assert decision.matched_by is MatchBasis.PROVENANCE
        assert decision.job_id == job.id

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_same_posting_from_another_source_matches_by_fingerprint(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        original = incoming_job()
        job = stored_job(original)
        await store(database, job)
        from_elsewhere = incoming_job(
            provenance={
                "source_key": "jobicy",
                "source_job_id": "98765",
                "source_url": "https://jobicy.example.com/jobs/98765",
            }
        )

        async with database.session() as session:
            decision = await decide(session, from_elsewhere)

        assert decision.outcome is DeduplicationOutcome.UNCHANGED
        assert decision.matched_by is MatchBasis.FINGERPRINT
        assert decision.job_id == job.id

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_fingerprint_match_that_differs_is_a_change(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        job = stored_job(incoming_job())
        await store(database, job)
        from_elsewhere = incoming_job(
            location="Berlin",
            application_url="https://jobicy.example.com/apply/98765",
            provenance={
                "source_key": "jobicy",
                "source_job_id": "98765",
                "source_url": "https://jobicy.example.com/jobs/98765",
            },
        )

        async with database.session() as session:
            decision = await decide(session, from_elsewhere)

        assert decision.outcome is DeduplicationOutcome.CHANGED
        assert decision.matched_by is MatchBasis.FINGERPRINT
        assert decision.job_id == job.id

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_several_matches_are_surfaced_rather_than_merged(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        incoming = incoming_job()
        first = stored_job(incoming)
        second = stored_job(incoming)
        await store(database, first, second)

        async with database.session() as session:
            decision = await decide(session, incoming)

        assert decision.outcome is DeduplicationOutcome.AMBIGUOUS
        assert decision.matched_by is MatchBasis.FINGERPRINT
        assert decision.job_id is None
        assert set(decision.candidate_job_ids) == {first.id, second.id}

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unregistered_source_falls_through_to_fingerprint_matching(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        job = stored_job(incoming_job())
        await store(database, job)

        async with database.session() as session:
            decision = await decide(session, incoming_job())

        assert decision.matched_by is MatchBasis.FINGERPRINT
        assert decision.job_id == job.id

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_different_posting_is_not_matched(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await store(database, stored_job(incoming_job()))
        different = incoming_job(company={"display_name": "Beispiel AG"})

        async with database.session() as session:
            decision = await decide(session, different)

        assert decision.outcome is DeduplicationOutcome.NEW

    run_database_test(database_url, exercise)


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "Staff Data Engineer"},
        {"description": "Something else entirely."},
        {"location": "Munich"},
        {"workplace_type": "hybrid"},
        {"employment_type": "contract"},
        {"application_url": "https://acme.example.com/jobs/other"},
        {"published_at": datetime(2026, 9, 1, tzinfo=UTC)},
        {"expires_at": datetime(2026, 12, 1, tzinfo=UTC)},
    ],
)
def test_every_canonical_field_counts_as_a_change(overrides: dict[str, Any]) -> None:
    original = incoming_job()

    assert has_material_change(stored_job(original), incoming_job(**overrides)) is True


def test_an_identical_job_is_not_a_change() -> None:
    original = incoming_job()

    assert has_material_change(stored_job(original), incoming_job()) is False


def test_provenance_alone_does_not_count_as_a_change() -> None:
    original = incoming_job()
    from_elsewhere = incoming_job(
        provenance={
            "source_key": "jobicy",
            "source_job_id": "98765",
            "source_url": "https://jobicy.example.com/jobs/98765",
        }
    )

    assert has_material_change(stored_job(original), from_elsewhere) is False
