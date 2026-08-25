"""Candidate-profile reads and idempotent profile and skill writes."""

from enum import StrEnum
from uuid import UUID

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.profiles.models import CandidateProfile, CandidateProfileSkill
from app.modules.profiles.queries import profile_skills_for_user
from app.modules.profiles.schemas import CandidateProfileUpdate
from app.modules.skills.models import SkillConcept
from app.modules.skills.resolution import (
    KnownSkillResolver,
    ResolutionStatus,
    load_default_resolver,
)


class ProfileNotFound(Exception):
    """Raised when a skill operation has no owner profile to act on."""


class SkillRefusalReason(StrEnum):
    AMBIGUOUS = "ambiguous_skill"
    UNMAPPED = "unknown_skill"


class SkillTermRefused(Exception):
    """A selected term cannot safely identify one canonical concept."""

    def __init__(self, reason: SkillRefusalReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


class SkillCatalogUnavailable(Exception):
    """The resolver and persisted canonical catalog are out of sync."""


SKILL_SEARCH_LIMIT = 10


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


async def list_profile_skills(
    session: AsyncSession,
    user_id: UUID,
) -> list[CandidateProfileSkill]:
    if await find_profile(session, user_id) is None:
        raise ProfileNotFound
    found = await session.execute(profile_skills_for_user(user_id))
    return list(found.scalars().all())


async def search_skill_concepts(
    session: AsyncSession,
    query: str,
) -> list[SkillConcept]:
    """Find a capped, deterministic set of persisted canonical concepts."""
    normalized = query.casefold()
    label = func.lower(SkillConcept.preferred_label)
    found = await session.scalars(
        select(SkillConcept)
        .where(label.contains(normalized, autoescape=True))
        .order_by(
            case((label.startswith(normalized, autoescape=True), 0), else_=1),
            label,
            SkillConcept.id,
        )
        .limit(SKILL_SEARCH_LIMIT)
    )
    return list(found.all())


async def _store_profile_skill(
    session: AsyncSession,
    user_id: UUID,
    profile_id: UUID,
    concept_id: UUID,
    vocabulary_version: str,
) -> CandidateProfileSkill:
    await session.execute(
        insert(CandidateProfileSkill)
        .values(
            profile_id=profile_id,
            concept_id=concept_id,
            vocabulary_version=vocabulary_version,
        )
        .on_conflict_do_nothing(index_elements=["profile_id", "concept_id"])
    )
    stored = (
        (
            await session.execute(
                profile_skills_for_user(user_id).where(
                    CandidateProfileSkill.concept_id == concept_id
                )
            )
        )
        .scalars()
        .one()
    )
    await session.commit()
    return stored


async def add_profile_skill(
    session: AsyncSession,
    user_id: UUID,
    term: str,
    *,
    resolver: KnownSkillResolver | None = None,
) -> CandidateProfileSkill:
    """Resolve and idempotently store one canonical concept for the owner."""
    profile = await find_profile(session, user_id)
    if profile is None:
        raise ProfileNotFound

    selected_resolver = resolver if resolver is not None else load_default_resolver()
    resolution = selected_resolver.resolve(term)
    if resolution.status is ResolutionStatus.AMBIGUOUS:
        raise SkillTermRefused(SkillRefusalReason.AMBIGUOUS)
    if resolution.status is ResolutionStatus.UNMAPPED:
        raise SkillTermRefused(SkillRefusalReason.UNMAPPED)

    concept = resolution.concepts[0]
    if await session.get(SkillConcept, concept.id) is None:
        raise SkillCatalogUnavailable

    return await _store_profile_skill(
        session,
        user_id,
        profile.id,
        concept.id,
        resolution.vocabulary_version,
    )


async def add_profile_skill_by_concept_id(
    session: AsyncSession,
    user_id: UUID,
    concept_id: UUID,
    *,
    resolver: KnownSkillResolver | None = None,
) -> CandidateProfileSkill:
    """Store one concept selected from the persisted canonical picker."""
    profile = await find_profile(session, user_id)
    if profile is None:
        raise ProfileNotFound
    if await session.get(SkillConcept, concept_id) is None:
        raise SkillTermRefused(SkillRefusalReason.UNMAPPED)

    selected_resolver = resolver if resolver is not None else load_default_resolver()
    return await _store_profile_skill(
        session,
        user_id,
        profile.id,
        concept_id,
        selected_resolver.vocabulary_version,
    )


async def remove_profile_skill(
    session: AsyncSession,
    user_id: UUID,
    concept_id: UUID,
) -> bool:
    profile = await find_profile(session, user_id)
    if profile is None:
        raise ProfileNotFound
    removed = await session.scalar(
        delete(CandidateProfileSkill)
        .where(
            CandidateProfileSkill.profile_id == profile.id,
            CandidateProfileSkill.concept_id == concept_id,
        )
        .returning(CandidateProfileSkill.concept_id)
    )
    await session.commit()
    return removed is not None
