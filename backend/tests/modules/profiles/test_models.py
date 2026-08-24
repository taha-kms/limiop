import asyncio
from collections.abc import Awaitable, Callable

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.session import Database
from app.modules.accounts.models import User
from app.modules.jobs.domain import EmploymentType, WorkplaceType
from app.modules.profiles.models import CandidateProfile

pytestmark = pytest.mark.integration


def run_database_test(
    database_url: PostgresDsn, test: Callable[[Database, User], Awaitable[None]]
) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                await session.execute(delete(User))
                user = User(email="ada@example.com", password_hash="x")
                session.add(user)
                await session.commit()
            await test(database, user)
        finally:
            async with database.session() as session:
                await session.execute(delete(User))
                await session.commit()
            await database.dispose()

    asyncio.run(run())


def test_a_partial_profile_is_incomplete(database_url: PostgresDsn) -> None:
    async def exercise(database: Database, user: User) -> None:
        async with database.session() as session:
            profile = CandidateProfile(user_id=user.id, display_name="Ada")
            session.add(profile)
            await session.commit()
            await session.refresh(profile)

        assert profile.profile_complete is False

    run_database_test(database_url, exercise)


def test_required_fields_make_a_profile_complete(database_url: PostgresDsn) -> None:
    async def exercise(database: Database, user: User) -> None:
        async with database.session() as session:
            profile = CandidateProfile(
                user_id=user.id,
                display_name="Ada Lovelace",
                location="London",
                workplace_types=[WorkplaceType.HYBRID],
                employment_types=[EmploymentType.FULL_TIME],
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)

        assert profile.profile_complete is True

    run_database_test(database_url, exercise)


def test_unspecified_preferences_do_not_make_a_profile_complete(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database, user: User) -> None:
        async with database.session() as session:
            profile = CandidateProfile(
                user_id=user.id,
                display_name="Ada Lovelace",
                location="London",
                workplace_types=[WorkplaceType.UNSPECIFIED],
                employment_types=[EmploymentType.UNSPECIFIED],
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)

        assert profile.profile_complete is False

    run_database_test(database_url, exercise)


def test_an_account_cannot_own_two_profiles(database_url: PostgresDsn) -> None:
    async def exercise(database: Database, user: User) -> None:
        async with database.session() as session:
            session.add_all(
                [
                    CandidateProfile(user_id=user.id),
                    CandidateProfile(user_id=user.id),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    run_database_test(database_url, exercise)


def test_profile_is_removed_with_its_account(database_url: PostgresDsn) -> None:
    async def exercise(database: Database, user: User) -> None:
        async with database.session() as session:
            profile = CandidateProfile(user_id=user.id)
            session.add(profile)
            await session.commit()
            profile_id = profile.id

        async with database.session() as session:
            stored_user = await session.get(User, user.id)
            assert stored_user is not None
            await session.delete(stored_user)
            await session.commit()

        async with database.session() as session:
            assert (
                await session.scalar(
                    select(CandidateProfile).where(CandidateProfile.id == profile_id)
                )
                is None
            )

    run_database_test(database_url, exercise)
