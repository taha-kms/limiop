"""Candidate-profile reads and idempotent partial writes."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.profiles.models import CandidateProfile
from app.modules.profiles.schemas import CandidateProfileUpdate


async def find_profile(session: AsyncSession, user_id: UUID) -> CandidateProfile | None:
    found = await session.execute(
        select(CandidateProfile).where(CandidateProfile.user_id == user_id)
    )
    return found.scalars().first()


async def save_profile(
    session: AsyncSession,
    user_id: UUID,
    update: CandidateProfileUpdate,
) -> CandidateProfile:
    """Create or update only the supplied canonical fields.

    The conflict path makes repeated or concurrent step submissions one
    idempotent write rather than two profiles fighting over the ownership
    constraint.
    """
    supplied = update.model_dump(exclude_unset=True)
    statement = (
        insert(CandidateProfile)
        .values(user_id=user_id, **supplied)
        .on_conflict_do_update(
            constraint="uq_candidate_profiles_user_id",
            set_={**supplied, "updated_at": func.now()},
        )
        .returning(CandidateProfile)
    )
    profile = (await session.execute(statement)).scalars().one()
    await session.commit()
    return profile
