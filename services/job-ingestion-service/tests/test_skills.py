"""Skill extraction attached to ingestion.

The pure planning rules are tested without a database, because `occurrences` is
the field most likely to be quietly wrong and the failure would look plausible
for weeks. The replacement and idempotence rules need real rows and a real
unique constraint, so those tests take a database or skip.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from platform_db.models import Company, Job, JobProvenance, JobSource
from platform_db.models.job_skills import JobSkill, JobSkillMention
from platform_db.models.skills import SkillAliasVersion, SkillConcept, SkillSurfaceForm
from platform_skills import EXTRACTOR_VERSION
from pydantic import PostgresDsn
from sqlalchemy import delete, func, select
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion import pipeline
from job_ingestion.contracts import IngestionSummary, RawPage, RawRecord
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration
from job_ingestion.pipeline import IngestionRun
from job_ingestion.schemas import NormalizedJob
from job_ingestion.skills import (
    ExtractionCounts,
    SkillVocabulary,
    collapse_whitespace,
    load_skill_vocabulary,
    plan_skills,
    store_job_skills,
)

PYTHON = UUID("11111111-1111-4111-8111-111111111111")
SQL_CONCEPT = UUID("22222222-2222-4222-8222-222222222222")
VERSION = "2026.08.28.1"
SEEN = datetime(2026, 8, 28, 10, tzinfo=UTC)
LATER = datetime(2026, 8, 28, 11, tzinfo=UTC)

VOCABULARY = SkillVocabulary(
    version=VERSION,
    terms={"python": PYTHON, "sql": SQL_CONCEPT, "data analysis": None},
)


def test_a_resolved_mention_becomes_one_concept_however_often_it_appears() -> None:
    plan = plan_skills("Python, python, and more Python.", VOCABULARY)

    assert plan.concepts == {PYTHON: "Python"}
    assert plan.counts.resolved == 1


def test_the_first_spelling_in_the_posting_is_the_one_stored() -> None:
    """So that re-running over unchanged text cannot rewrite the stored form."""
    assert plan_skills("PYTHON then python", VOCABULARY).concepts == {PYTHON: "PYTHON"}
    assert plan_skills("python then PYTHON", VOCABULARY).concepts == {PYTHON: "python"}


def test_an_unresolved_mention_never_reaches_the_concepts() -> None:
    plan = plan_skills("We need data analysis skills.", VOCABULARY)

    assert plan.concepts == {}
    assert plan.observations == {"data analysis": ("data analysis", 1)}


def test_occurrences_counts_appearances_in_the_text() -> None:
    plan = plan_skills("data analysis, then more data analysis, and data analysis", VOCABULARY)

    assert plan.observations == {"data analysis": ("data analysis", 3)}
    assert plan.counts.unknown == 3


def test_occurrences_groups_by_the_spelling_the_unique_key_uses() -> None:
    """The grouping key and the conflict target must be the same tuple.

    `uq_job_skill_mentions_job_surface_extractor_alias` keys on the raw surface
    form, so two spellings are two rows rather than one row of three.
    """
    plan = plan_skills("Data Analysis and data analysis and data analysis", VOCABULARY)

    assert plan.observations == {
        "Data Analysis": ("data analysis", 1),
        "data analysis": ("data analysis", 2),
    }


def test_a_phrase_matched_across_flattened_markup_is_stored_as_one_line() -> None:
    """Descriptions are flattened from markup, so a match can span newlines."""
    plan = plan_skills("skills in data\n\n   analysis matter", VOCABULARY)

    assert plan.observations == {"data analysis": ("data analysis", 1)}


def test_collapsing_whitespace_keeps_the_employer_spelling() -> None:
    assert collapse_whitespace("Data\n  Analysis") == "Data Analysis"


def test_a_posting_naming_nothing_plans_nothing() -> None:
    plan = plan_skills("We are hiring a friendly person.", VOCABULARY)

    assert plan.concepts == {}
    assert plan.observations == {}
    assert plan.counts.resolved == 0
    assert plan.counts.unknown == 0


def test_a_term_outside_the_vocabulary_is_invisible_to_the_extractor() -> None:
    """The extractor matches a vocabulary; it does not discover unknown skills.

    This is why `job_skill_mentions` stays empty against a vocabulary with no
    ambiguous forms, and why the observation inbox cannot yet answer the
    unknown-skill question the gate evaluation deferred to it.
    """
    plan = plan_skills("Deep experience with Kubernetes and Rust.", VOCABULARY)

    assert plan.concepts == {}
    assert plan.observations == {}


SOURCE = SourceRegistration(
    key="arbeitnow",
    display_name="Arbeitnow",
    base_url="https://www.arbeitnow.com/api/job-board-api",
)


class OnePage:
    """The smallest client the run will accept: one record, then the end."""

    def __init__(self, record: dict[str, object]) -> None:
        self._record = record
        self.reached_the_end = False

    @property
    def source_key(self) -> str:
        return SOURCE.key

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        yield RawPage(records=(self._record,))
        self.reached_the_end = True


class PassThrough:
    """Validation and normalization are not what these tests are about."""

    def validate(self, raw: RawRecord) -> RawRecord:
        return raw

    def normalize(self, record: RawRecord, raw: RawRecord) -> NormalizedJob:
        return NormalizedJob.model_validate(record)


async def ingest_one(
    database: Database,
    description: str,
    *,
    break_extraction: bool = False,
) -> IngestionSummary:
    """Run the real pipeline over exactly one posting."""
    record: dict[str, object] = {
        "company": {"display_name": "Acme GmbH"},
        "title": "Engineer",
        "description": description,
        "application_url": "https://acme.example.com/jobs/engineer",
        "provenance": {
            "source_key": SOURCE.key,
            "source_job_id": "external-1",
            "source_url": "https://acme.example.com/jobs/engineer",
            "raw_payload": {},
        },
    }
    run = IngestionRun(
        client=OnePage(record),
        validator=PassThrough(),
        normalizer=PassThrough(),
        source=SOURCE,
        max_records=10,
    )
    if not break_extraction:
        return await run.execute(database, clock=lambda: SEEN)

    # A genuine PostgreSQL error raised inside the extraction savepoint, rather
    # than a mocked exception: what is under test is that the real rollback
    # leaves the job behind.
    async def explode(session: AsyncSession, **_: object) -> ExtractionCounts:
        await session.execute(sql("SELECT 1 / 0"))
        raise AssertionError("unreachable")

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(pipeline, "store_job_skills", explode)
        return await run.execute(database, clock=lambda: SEEN)


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def clear(database: Database) -> None:
        async with database.session() as session:
            await session.execute(delete(JobSkillMention))
            await session.execute(delete(JobSkill))
            await session.execute(delete(JobProvenance))
            await session.execute(delete(Job))
            await session.execute(delete(Company))
            await session.execute(delete(JobSource))
            await session.execute(delete(SkillSurfaceForm))
            await session.execute(delete(SkillConcept))
            await session.execute(delete(SkillAliasVersion))
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


async def publish_vocabulary(database: Database) -> None:
    async with database.session() as session:
        session.add(SkillAliasVersion(version=VERSION))
        session.add(SkillConcept(id=PYTHON, preferred_label="Python"))
        session.add(SkillConcept(id=SQL_CONCEPT, preferred_label="SQL"))
        await session.flush()
        session.add_all(
            [
                SkillSurfaceForm(
                    alias_version=VERSION,
                    concept_id=PYTHON,
                    surface_form="Python",
                    normalized_form="python",
                ),
                SkillSurfaceForm(
                    alias_version=VERSION,
                    concept_id=SQL_CONCEPT,
                    surface_form="SQL",
                    normalized_form="sql",
                ),
            ]
        )
        await session.commit()


async def store_job(database: Database, description: str) -> UUID:
    job_id = uuid4()
    async with database.session() as session:
        company = Company(display_name="Acme GmbH", normalized_name="acme gmbh")
        session.add(company)
        await session.flush()
        session.add(
            Job(
                id=job_id,
                company_id=company.id,
                title="Engineer",
                description=description,
                application_url="https://acme.example.com/jobs/engineer",
                match_key="acme gmbh|engineer",
            )
        )
        await session.commit()
    return job_id


async def skill_rows(database: Database, job_id: UUID) -> list[tuple[UUID, str, str]]:
    async with database.session() as session:
        rows = await session.execute(
            select(JobSkill.concept_id, JobSkill.surface_form, JobSkill.alias_version).where(
                JobSkill.job_id == job_id
            )
        )
        return sorted((row[0], row[1], row[2]) for row in rows)


@pytest.mark.integration
def test_the_published_vocabulary_is_read_back_from_the_database(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        await publish_vocabulary(database)
        async with database.session() as session:
            vocabulary = await load_skill_vocabulary(session)

        assert vocabulary is not None
        assert vocabulary.version == VERSION
        assert vocabulary.terms == {"Python": PYTHON, "SQL": SQL_CONCEPT}

    run_database_test(database_url, test)


@pytest.mark.integration
def test_no_published_vocabulary_reports_absence_rather_than_an_empty_one(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        async with database.session() as session:
            assert await load_skill_vocabulary(session) is None

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_version_that_was_never_published_is_refused(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        await publish_vocabulary(database)
        async with database.session() as session:
            assert await load_skill_vocabulary(session, version="1999.01.01.1") is None

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_posting_gets_one_row_per_concept(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        await publish_vocabulary(database)
        job_id = await store_job(database, "Python, Python, and SQL.")
        async with database.session() as session:
            vocabulary = await load_skill_vocabulary(session)
            assert vocabulary is not None
            counts = await store_job_skills(
                session,
                job_id=job_id,
                text="Python, Python, and SQL.",
                vocabulary=vocabulary,
                seen_at=SEEN,
            )
            await session.commit()

        assert counts.resolved == 2
        assert await skill_rows(database, job_id) == sorted(
            [(PYTHON, "Python", VERSION), (SQL_CONCEPT, "SQL", VERSION)]
        )

    run_database_test(database_url, test)


@pytest.mark.integration
def test_re_extracting_unchanged_text_changes_nothing(database_url: PostgresDsn) -> None:
    """The hourly re-run. Two rows in, two rows out, and no counter moved."""

    async def test(database: Database) -> None:
        await publish_vocabulary(database)
        text = "Python and SQL and Python."
        job_id = await store_job(database, text)

        async def extract(seen_at: datetime) -> None:
            async with database.session() as session:
                vocabulary = await load_skill_vocabulary(session)
                assert vocabulary is not None
                await store_job_skills(
                    session, job_id=job_id, text=text, vocabulary=vocabulary, seen_at=seen_at
                )
                await session.commit()

        await extract(SEEN)
        first = await skill_rows(database, job_id)
        for _ in range(4):
            await extract(LATER)

        assert await skill_rows(database, job_id) == first

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_posting_that_stops_naming_a_skill_stops_carrying_it(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        await publish_vocabulary(database)
        job_id = await store_job(database, "Python and SQL.")

        async def extract(text: str) -> None:
            async with database.session() as session:
                vocabulary = await load_skill_vocabulary(session)
                assert vocabulary is not None
                await store_job_skills(
                    session, job_id=job_id, text=text, vocabulary=vocabulary, seen_at=SEEN
                )
                await session.commit()

        await extract("Python and SQL.")
        assert len(await skill_rows(database, job_id)) == 2

        await extract("Python only now.")
        assert await skill_rows(database, job_id) == [(PYTHON, "Python", VERSION)]

    run_database_test(database_url, test)


@pytest.mark.integration
def test_an_unresolved_mention_is_observed_without_inflating_across_runs(
    database_url: PostgresDsn,
) -> None:
    """Ambiguity is the only way a mention goes unresolved today.

    A surface form naming two concepts is refused for matching and recorded as
    an observation. Re-running must recompute `occurrences` from the text, not
    add to it: an incrementing counter looks plausible for weeks before anyone
    notices the frequency evidence is worthless.
    """

    async def test(database: Database) -> None:
        await publish_vocabulary(database)
        async with database.session() as session:
            # One spelling, two concepts. The extractor is told None, not a guess.
            session.add(
                SkillSurfaceForm(
                    alias_version=VERSION,
                    concept_id=PYTHON,
                    surface_form="stack",
                    normalized_form="stack",
                )
            )
            session.add(
                SkillSurfaceForm(
                    alias_version=VERSION,
                    concept_id=SQL_CONCEPT,
                    surface_form="stack",
                    normalized_form="stack",
                )
            )
            await session.commit()

        text = "our stack, the whole stack, every stack"
        job_id = await store_job(database, text)

        async def extract(seen_at: datetime) -> None:
            async with database.session() as session:
                vocabulary = await load_skill_vocabulary(session)
                assert vocabulary is not None
                assert vocabulary.terms["stack"] is None
                await store_job_skills(
                    session, job_id=job_id, text=text, vocabulary=vocabulary, seen_at=seen_at
                )
                await session.commit()

        async def observations() -> list[tuple[str, int, datetime, datetime]]:
            async with database.session() as session:
                rows = await session.execute(
                    select(
                        JobSkillMention.surface_form,
                        JobSkillMention.occurrences,
                        JobSkillMention.first_seen_at,
                        JobSkillMention.last_seen_at,
                    ).where(JobSkillMention.job_id == job_id)
                )
                return [(r[0], r[1], r[2], r[3]) for r in rows]

        await extract(SEEN)
        assert await observations() == [("stack", 3, SEEN, SEEN)]

        for _ in range(5):
            await extract(LATER)

        # Still three: the count came from the text, not from the runs.
        assert await observations() == [("stack", 3, SEEN, LATER)]

        async with database.session() as session:
            stored = await session.scalar(
                select(JobSkillMention.extractor_version).where(JobSkillMention.job_id == job_id)
            )
        assert stored == EXTRACTOR_VERSION
        assert await skill_rows(database, job_id) == []

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_run_reports_what_extraction_did(database_url: PostgresDsn) -> None:
    """The counts have to reach the summary, or a silent no-op looks like a run."""

    async def test(database: Database) -> None:
        await publish_vocabulary(database)
        summary = await ingest_one(database, "We need Python and SQL.")

        assert summary.alias_version == VERSION
        assert summary.mentions_resolved == 2
        assert summary.mentions_unknown == 0
        assert summary.mentions_discarded == summary.mentions_unknown
        assert summary.extraction_failed == 0
        assert summary.created == 1

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_run_without_a_published_vocabulary_stores_the_job_anyway(
    database_url: PostgresDsn,
) -> None:
    """Extraction is enrichment. Nothing published means nothing extracted."""

    async def test(database: Database) -> None:
        summary = await ingest_one(database, "We need Python and SQL.")

        assert summary.created == 1
        assert summary.alias_version is None
        assert summary.mentions_resolved == 0
        assert not summary.failures
        assert summary.processing_complete

    run_database_test(database_url, test)


@pytest.mark.integration
def test_a_failure_while_writing_skills_still_stores_the_posting(
    database_url: PostgresDsn,
) -> None:
    """And is kept out of `failures`, which gates withdrawal.

    A run whose extraction failed is not a run that could not read its source,
    and treating it as one would stop reconciliation from ever concluding a
    posting is gone.
    """

    async def test(database: Database) -> None:
        await publish_vocabulary(database)
        summary = await ingest_one(database, "We need Python.", break_extraction=True)

        assert summary.created == 1
        assert summary.extraction_failed == 1
        assert summary.mentions_resolved == 0
        assert not summary.failures
        assert summary.processing_complete

        async with database.session() as session:
            assert await session.scalar(select(func.count()).select_from(Job)) == 1
            assert await session.scalar(select(func.count()).select_from(JobSkill)) == 0

    run_database_test(database_url, test)


@pytest.mark.integration
def test_an_unchanged_posting_keeps_its_skills_across_runs(
    database_url: PostgresDsn,
) -> None:
    """The second run of a source is a no-op, and a no-op must not strip skills.

    The persistence outcome for an unchanged posting is SKIPPED, so extraction
    has to key off the job row existing rather than off the record changing.
    """

    async def test(database: Database) -> None:
        await publish_vocabulary(database)
        first = await ingest_one(database, "We need Python and SQL.")
        second = await ingest_one(database, "We need Python and SQL.")

        assert first.created == 1
        assert second.created == 0
        assert second.skipped == 1
        assert second.mentions_resolved == 2

        async with database.session() as session:
            assert await session.scalar(select(func.count()).select_from(JobSkill)) == 2

    run_database_test(database_url, test)
