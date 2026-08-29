"""Reading skills out of a parsed CV onto the candidate's profile."""

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from uuid import UUID, uuid4

import pytest
from platform_db.models import SkillConcept
from pydantic import PostgresDsn
from sqlalchemy import create_engine, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Database
from app.modules.accounts.models import User
from app.modules.cvs.skills import concepts_in, store_cv_skills
from app.modules.profiles.models import CandidateProfile, CandidateProfileSkill, SkillSource
from app.modules.skills.resolution import AliasTableDocument, KnownSkillResolver

pytestmark = pytest.mark.integration

VERSION = "cv-skills.test.1"
PYTHON = UUID("bbbbbbbb-0000-4000-8000-000000000001")
SQL = UUID("bbbbbbbb-0000-4000-8000-000000000002")
DESIGN = UUID("bbbbbbbb-0000-4000-8000-000000000003")
CONCEPTS = {PYTHON: "Python", SQL: "SQL", DESIGN: "Product design"}


def resolver() -> KnownSkillResolver:
    return KnownSkillResolver(
        AliasTableDocument.model_validate(
            {
                "schema_version": 1,
                "vocabulary_version": VERSION,
                "concepts": [
                    {"id": concept, "preferred_label": label} for concept, label in CONCEPTS.items()
                ],
                "surface_forms": [
                    {"surface_form": "Python", "concept_ids": [PYTHON]},
                    {"surface_form": "SQL", "concept_ids": [SQL]},
                    {"surface_form": "Postgres", "concept_ids": [SQL]},
                    {"surface_form": "product design", "concept_ids": [DESIGN]},
                ],
            }
        )
    )


RESOLVER = resolver()


def test_a_cv_naming_a_skill_resolves_it() -> None:
    assert concepts_in("Five years of Python.", RESOLVER) == (PYTHON,)


def test_an_alias_resolves_to_the_same_concept_as_its_preferred_label() -> None:
    assert concepts_in("Postgres and SQL.", RESOLVER) == (SQL,)


def test_a_term_outside_the_vocabulary_is_invisible() -> None:
    """The extractor matches a vocabulary; it does not discover skills."""
    assert concepts_in("Deep experience with Kubernetes and Rust.", RESOLVER) == ()


def test_an_empty_cv_names_nothing() -> None:
    assert concepts_in("", RESOLVER) == ()


def test_repeating_a_skill_still_names_it_once() -> None:
    assert concepts_in("Python, Python, and more Python.", RESOLVER) == (PYTHON,)


def test_the_same_text_always_resolves_the_same_way() -> None:
    assert concepts_in("SQL and Python", RESOLVER) == concepts_in("Python and SQL", RESOLVER)


@pytest.fixture
def profile(database_url: PostgresDsn) -> Iterator[UUID]:
    """One candidate profile and the concepts a CV could name, cleared around."""
    engine = create_engine(str(database_url))
    user_id, profile_id = uuid4(), uuid4()

    def clear() -> None:
        with engine.begin() as connection:
            connection.execute(
                delete(CandidateProfileSkill).where(CandidateProfileSkill.profile_id == profile_id)
            )
            connection.execute(delete(CandidateProfile).where(CandidateProfile.id == profile_id))
            connection.execute(delete(User).where(User.id == user_id))
            connection.execute(delete(SkillConcept).where(SkillConcept.id.in_(CONCEPTS)))

    clear()
    with engine.begin() as connection:
        connection.execute(
            insert(SkillConcept),
            [{"id": concept, "preferred_label": label} for concept, label in CONCEPTS.items()],
        )
        connection.execute(
            insert(User),
            [
                {
                    "id": user_id,
                    "email": f"cv-{user_id}@example.com",
                    "normalized_email": f"cv-{user_id}@example.com",
                    "password_hash": "x",
                }
            ],
        )
        connection.execute(insert(CandidateProfile), [{"id": profile_id, "user_id": user_id}])

    try:
        yield profile_id
    finally:
        clear()
        engine.dispose()


def run(database_url: PostgresDsn, work: Callable[[AsyncSession], Awaitable[None]]) -> None:
    async def go() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                await work(session)
                await session.commit()
        finally:
            await database.dispose()

    asyncio.run(go())


def stored(database_url: PostgresDsn, profile_id: UUID) -> dict[UUID, str]:
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        rows = connection.execute(
            select(CandidateProfileSkill.concept_id, CandidateProfileSkill.source).where(
                CandidateProfileSkill.profile_id == profile_id
            )
        ).all()
    engine.dispose()
    return {row[0]: row[1] for row in rows}


def test_extracted_skills_reach_the_profile(database_url: PostgresDsn, profile: UUID) -> None:
    async def work(session: AsyncSession) -> None:
        result = await store_cv_skills(
            session, profile_id=profile, text="Python and SQL.", resolver=RESOLVER
        )
        assert result.added == tuple(sorted((PYTHON, SQL)))
        assert result.vocabulary_version == VERSION

    run(database_url, work)

    assert stored(database_url, profile) == {PYTHON: SkillSource.CV, SQL: SkillSource.CV}


def test_reading_the_same_cv_again_changes_nothing(
    database_url: PostgresDsn, profile: UUID
) -> None:
    async def work(session: AsyncSession) -> None:
        for _ in range(3):
            await store_cv_skills(
                session, profile_id=profile, text="Python and SQL.", resolver=RESOLVER
            )

    run(database_url, work)

    assert stored(database_url, profile) == {PYTHON: SkillSource.CV, SQL: SkillSource.CV}


def test_a_new_cv_replaces_the_old_one_rather_than_adding_to_it(
    database_url: PostgresDsn, profile: UUID
) -> None:
    async def work(session: AsyncSession) -> None:
        await store_cv_skills(
            session, profile_id=profile, text="Python and SQL.", resolver=RESOLVER
        )
        await store_cv_skills(
            session, profile_id=profile, text="Only product design now.", resolver=RESOLVER
        )

    run(database_url, work)

    assert stored(database_url, profile) == {DESIGN: SkillSource.CV}


def test_a_hand_picked_skill_survives_a_cv_that_never_mentions_it(
    database_url: PostgresDsn, profile: UUID
) -> None:
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(
            insert(CandidateProfileSkill),
            [
                {
                    "profile_id": profile,
                    "concept_id": DESIGN,
                    "vocabulary_version": VERSION,
                    "source": SkillSource.MANUAL,
                }
            ],
        )
    engine.dispose()

    async def work(session: AsyncSession) -> None:
        await store_cv_skills(session, profile_id=profile, text="Python.", resolver=RESOLVER)

    run(database_url, work)

    assert stored(database_url, profile) == {DESIGN: SkillSource.MANUAL, PYTHON: SkillSource.CV}


def test_a_skill_in_both_stays_the_candidates_own_choice(
    database_url: PostgresDsn, profile: UUID
) -> None:
    """A deliberate choice outranks an inference from a document.

    Otherwise a later upload silently rewrites how a skill got there, and
    removing that CV would then take the skill with it.
    """
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(
            insert(CandidateProfileSkill),
            [
                {
                    "profile_id": profile,
                    "concept_id": PYTHON,
                    "vocabulary_version": VERSION,
                    "source": SkillSource.MANUAL,
                }
            ],
        )
    engine.dispose()

    async def work(session: AsyncSession) -> None:
        result = await store_cv_skills(
            session, profile_id=profile, text="Python and SQL.", resolver=RESOLVER
        )
        assert result.added == (SQL,)
        assert result.already_chosen == (PYTHON,)
        assert result.found == 2

    run(database_url, work)

    assert stored(database_url, profile) == {PYTHON: SkillSource.MANUAL, SQL: SkillSource.CV}


def test_a_cv_naming_nothing_clears_what_the_last_one_left(
    database_url: PostgresDsn, profile: UUID
) -> None:
    async def work(session: AsyncSession) -> None:
        await store_cv_skills(session, profile_id=profile, text="Python.", resolver=RESOLVER)
        result = await store_cv_skills(
            session, profile_id=profile, text="Nothing recognisable.", resolver=RESOLVER
        )
        assert result.found == 0

    run(database_url, work)

    assert stored(database_url, profile) == {}
