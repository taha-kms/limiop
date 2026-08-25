import asyncio
from uuid import uuid4

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete, select

from app.db.session import Database
from app.modules.accounts.models import User
from app.modules.jobs.domain import EmploymentType, WorkplaceType
from app.modules.profiles.models import CandidateProfile, CandidateProfileSkill
from app.modules.profiles.queries import matching_ready
from app.modules.skills.models import SkillConcept


def test_matching_readiness_uses_a_correlated_stored_skill_count() -> None:
    statement = select(CandidateProfile.id).where(matching_ready())

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "candidate_profiles.profile_complete IS true" in compiled
    assert "FROM candidate_profile_skills" in compiled
    assert "candidate_profile_skills.profile_id = candidate_profiles.id" in compiled
    assert ">= 1" in compiled


@pytest.mark.integration
def test_matching_readiness_reflects_the_current_owner_skills(
    database_url: PostgresDsn,
) -> None:
    async def exercise() -> None:
        database = Database(database_url)
        concept = SkillConcept(id=uuid4(), preferred_label="Query test skill")
        ready_user = User(email="ready@example.com", password_hash="x")
        waiting_user = User(email="waiting@example.com", password_hash="x")
        try:
            async with database.session() as session:
                await session.execute(delete(User))
                session.add_all([concept, ready_user, waiting_user])
                await session.flush()
                ready_profile = CandidateProfile(
                    user_id=ready_user.id,
                    display_name="Ready",
                    location="Rome",
                    workplace_types=[WorkplaceType.REMOTE],
                    employment_types=[EmploymentType.FULL_TIME],
                )
                waiting_profile = CandidateProfile(
                    user_id=waiting_user.id,
                    display_name="Waiting",
                    location="Rome",
                    workplace_types=[WorkplaceType.REMOTE],
                    employment_types=[EmploymentType.FULL_TIME],
                )
                session.add_all([ready_profile, waiting_profile])
                await session.flush()
                session.add(
                    CandidateProfileSkill(
                        profile_id=ready_profile.id,
                        concept_id=concept.id,
                        vocabulary_version="query.test.1",
                    )
                )
                await session.commit()

            async with database.session() as session:
                ready_ids = set(
                    (await session.execute(select(CandidateProfile.id).where(matching_ready())))
                    .scalars()
                    .all()
                )

            assert ready_ids == {ready_profile.id}
        finally:
            async with database.session() as session:
                await session.execute(delete(User))
                await session.execute(delete(SkillConcept).where(SkillConcept.id == concept.id))
                await session.commit()
            await database.dispose()

    asyncio.run(exercise())
