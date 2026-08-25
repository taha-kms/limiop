import asyncio
from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from platform_db.base import Base
from platform_db.models import SkillConcept
from pydantic import PostgresDsn
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.session import Database
from app.modules.accounts.models import User
from app.modules.profiles.models import CandidateProfile, CandidateProfileSkill

pytestmark = pytest.mark.integration


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database, User, SkillConcept], Awaitable[None]],
) -> None:
    async def run() -> None:
        database = Database(database_url)
        user = User(email=f"{uuid4()}@example.com", password_hash="x")
        concept = SkillConcept(id=uuid4(), preferred_label="Profile skill test concept")
        try:
            async with database.session() as session:
                session.add_all([user, concept])
                await session.commit()
            await test(database, user, concept)
        finally:
            async with database.session() as session:
                await session.execute(delete(User).where(User.id == user.id))
                await session.execute(delete(SkillConcept).where(SkillConcept.id == concept.id))
                await session.commit()
            await database.dispose()

    asyncio.run(run())


def test_profile_skill_model_uses_shared_metadata() -> None:
    assert CandidateProfileSkill.metadata is Base.metadata


def test_one_profile_concept_pair_cannot_be_duplicated(database_url: PostgresDsn) -> None:
    async def exercise(database: Database, user: User, concept: SkillConcept) -> None:
        async with database.session() as session:
            profile = CandidateProfile(user_id=user.id)
            session.add(profile)
            await session.flush()
            session.add_all(
                [
                    CandidateProfileSkill(
                        profile_id=profile.id,
                        concept_id=concept.id,
                        vocabulary_version="test.1",
                    ),
                    CandidateProfileSkill(
                        profile_id=profile.id,
                        concept_id=concept.id,
                        vocabulary_version="test.2",
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    run_database_test(database_url, exercise)


def test_profile_deletion_cascades_but_concept_deletion_is_restricted(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database, user: User, concept: SkillConcept) -> None:
        async with database.session() as session:
            profile = CandidateProfile(user_id=user.id)
            session.add(profile)
            await session.flush()
            skill = CandidateProfileSkill(
                profile_id=profile.id,
                concept_id=concept.id,
                vocabulary_version="test.1",
            )
            session.add(skill)
            await session.commit()
            profile_id = profile.id

        async with database.session() as session:
            stored_concept = await session.get(SkillConcept, concept.id)
            assert stored_concept is not None
            await session.delete(stored_concept)
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

        async with database.session() as session:
            stored_profile = await session.get(CandidateProfile, profile_id)
            assert stored_profile is not None
            await session.delete(stored_profile)
            await session.commit()

        async with database.session() as session:
            assert (
                await session.scalar(
                    select(CandidateProfileSkill).where(
                        CandidateProfileSkill.profile_id == profile_id
                    )
                )
                is None
            )
            assert await session.get(SkillConcept, concept.id) is not None

    run_database_test(database_url, exercise)
