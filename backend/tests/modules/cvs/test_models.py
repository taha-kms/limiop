import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.db.session import Database
from app.modules.accounts.models import User
from app.modules.cvs.models import (
    CV,
    CVProcessingState,
    InvalidCVProcessingTransition,
)

pytestmark = pytest.mark.integration


def run_database_test(
    database_url: PostgresDsn, test: Callable[[Database], Awaitable[None]]
) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                await session.execute(delete(User))
                await session.commit()
            await test(database)
        finally:
            async with database.session() as session:
                await session.execute(delete(User))
                await session.commit()
            await database.dispose()

    asyncio.run(run())


def cv_for(owner: User, **overrides: object) -> CV:
    values: dict[str, object] = {
        "owner_id": owner.id,
        "storage_key": "cvs/one.pdf",
        "checksum_sha256": "a" * 64,
        "media_type": "application/pdf",
        "size_bytes": 1024,
    }
    values.update(overrides)
    return CV(**values)


async def persisted_user(database: Database) -> User:
    async with database.session() as session:
        user = User(email=f"{uuid4()}@example.com", password_hash="x")
        session.add(user)
        await session.commit()
        return user


def test_a_cv_starts_pending_and_keeps_only_external_storage_metadata(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        user = await persisted_user(database)
        async with database.session() as session:
            session.add(cv_for(user))
            await session.commit()
        async with database.session() as session:
            cv = (await session.execute(select(CV))).scalars().one()
            assert cv.owner_id == user.id
            assert cv.processing_state is CVProcessingState.PENDING
            assert cv.created_at.tzinfo is not None
            assert cv.updated_at.tzinfo is not None
            assert "bytes" not in CV.__table__.columns

    run_database_test(database_url, test)


def test_deleting_an_owner_cascades_to_their_cv_metadata(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        user = await persisted_user(database)
        async with database.session() as session:
            session.add(cv_for(user))
            await session.commit()
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()
        async with database.session() as session:
            assert (await session.execute(select(CV))).scalars().all() == []

    run_database_test(database_url, test)


def test_a_storage_key_cannot_identify_two_cvs(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        user = await persisted_user(database)
        async with database.session() as session:
            session.add_all([cv_for(user), cv_for(user)])
            with pytest.raises(IntegrityError):
                await session.commit()

    run_database_test(database_url, test)


@pytest.mark.parametrize(
    "overrides",
    [
        {"storage_key": ""},
        {"storage_key": " padded "},
        {"checksum_sha256": "A" * 64},
        {"checksum_sha256": "a" * 63},
        {"media_type": "text/plain"},
        {"size_bytes": 0},
        {"size_bytes": -1},
    ],
)
def test_invalid_storage_metadata_is_rejected_by_postgresql(
    database_url: PostgresDsn, overrides: dict[str, object]
) -> None:
    async def test(database: Database) -> None:
        user = await persisted_user(database)
        async with database.session() as session:
            session.add(cv_for(user, **overrides))
            with pytest.raises(IntegrityError):
                await session.commit()

    run_database_test(database_url, test)


def test_a_cv_cannot_reference_an_owner_who_does_not_exist(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        missing = User(id=uuid4(), email="missing@example.com", password_hash="x")
        async with database.session() as session:
            session.add(cv_for(missing))
            with pytest.raises(IntegrityError):
                await session.commit()

    run_database_test(database_url, test)


def test_postgresql_rejects_a_processing_state_outside_the_vocabulary(
    database_url: PostgresDsn,
) -> None:
    async def test(database: Database) -> None:
        user = await persisted_user(database)
        async with database.session() as session:
            session.add(cv_for(user))
            await session.commit()
            with pytest.raises(IntegrityError):
                await session.execute(text("UPDATE cvs SET processing_state = 'invented'"))

    run_database_test(database_url, test)


def test_the_processing_lifecycle_and_retry_are_explicit() -> None:
    cv = cv_for(User(id=uuid4(), email="state@example.com", password_hash="x"))
    assert cv.processing_state is None

    cv.processing_state = CVProcessingState.PENDING
    cv.transition_to(CVProcessingState.PROCESSING)
    cv.transition_to(CVProcessingState.FAILED)
    cv.transition_to(CVProcessingState.PROCESSING)
    cv.transition_to(CVProcessingState.PROCESSED)

    assert cv.processing_state is CVProcessingState.PROCESSED


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (CVProcessingState.PENDING, CVProcessingState.PROCESSED),
        (CVProcessingState.PENDING, CVProcessingState.FAILED),
        (CVProcessingState.PROCESSING, CVProcessingState.PENDING),
        (CVProcessingState.PROCESSED, CVProcessingState.PROCESSING),
        (CVProcessingState.FAILED, CVProcessingState.PROCESSED),
    ],
)
def test_invalid_processing_state_transitions_are_rejected(
    start: CVProcessingState, target: CVProcessingState
) -> None:
    cv = cv_for(User(id=uuid4(), email="state@example.com", password_hash="x"))
    cv.processing_state = CVProcessingState.PENDING
    if start is CVProcessingState.PROCESSING:
        cv.transition_to(CVProcessingState.PROCESSING)
    elif start is CVProcessingState.PROCESSED:
        cv.transition_to(CVProcessingState.PROCESSING)
        cv.transition_to(CVProcessingState.PROCESSED)
    elif start is CVProcessingState.FAILED:
        cv.transition_to(CVProcessingState.PROCESSING)
        cv.transition_to(CVProcessingState.FAILED)

    with pytest.raises(InvalidCVProcessingTransition):
        cv.transition_to(target)


def test_a_cv_cannot_be_created_in_a_later_processing_state() -> None:
    user = User(id=uuid4(), email="state@example.com", password_hash="x")
    with pytest.raises(InvalidCVProcessingTransition, match="start pending"):
        cv_for(user, processing_state=CVProcessingState.PROCESSED)


def test_the_database_rejects_timestamps_in_reverse_order(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        user = await persisted_user(database)
        now = datetime.now(UTC)
        async with database.session() as session:
            session.add(
                cv_for(
                    user,
                    created_at=now,
                    updated_at=now - timedelta(seconds=1),
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    run_database_test(database_url, test)


def test_sqlalchemy_refuses_an_unknown_state_before_persistence(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        user = await persisted_user(database)
        async with database.session() as session:
            cv = cv_for(user)
            cv.__dict__["processing_state"] = "invented"
            session.add(cv)
            with pytest.raises(StatementError):
                await session.commit()

    run_database_test(database_url, test)
