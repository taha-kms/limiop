"""Reading skills out of a parsed CV and onto the candidate's profile.

The same extractor ingestion runs over a posting, run over the other side of
the match. One vocabulary, one set of concepts, and a candidate skill that means
the same thing as a job skill — which is the whole reason matching is a set
intersection rather than a similarity.

Skills land in `candidate_profile_skills`, where the picker already puts them.
A settled decision says the two routes into a profile must produce the same
profile and that neither is the other's fallback; two skill tables would make
that false at the schema level.
"""

from dataclasses import dataclass
from uuid import UUID

from platform_skills import extract_mentions
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.profiles.models import CandidateProfileSkill, SkillSource
from app.modules.skills.resolution import KnownSkillResolver, load_default_resolver


@dataclass(frozen=True, slots=True)
class ExtractedCVSkills:
    """What one read of a CV put on the profile."""

    vocabulary_version: str
    added: tuple[UUID, ...]
    already_chosen: tuple[UUID, ...]

    @property
    def found(self) -> int:
        return len(self.added) + len(self.already_chosen)


def concepts_in(text: str, resolver: KnownSkillResolver) -> tuple[UUID, ...]:
    """The canonical concepts a CV names, sorted and without repeats.

    An unresolved mention is dropped rather than recorded. The admission gate is
    closed, and the observation inbox that would hold it is fed by ingestion,
    where a mention can be tied back to a posting anyone can read. A candidate's
    CV is not that, and putting private text into an evidence table nothing
    matches against would be collecting it for no stated purpose.
    """
    vocabulary = {
        form.surface_form: form.concept_ids[0] if len(form.concept_ids) == 1 else None
        for form in resolver.document.surface_forms
    }
    found = {
        mention.concept_id
        for mention in extract_mentions(text, vocabulary)
        if mention.concept_id is not None
    }
    return tuple(sorted(found))


async def store_cv_skills(
    session: AsyncSession,
    *,
    profile_id: UUID,
    text: str,
    resolver: KnownSkillResolver | None = None,
) -> ExtractedCVSkills:
    """Replace this profile's CV-derived skills with what the CV says now.

    Only the rows a previous read wrote are removed. A concept the candidate
    picked by hand survives, and a concept in both stays theirs: the insert
    declines the conflict rather than overwriting the source, so re-reading a CV
    can never quietly unpick a deliberate choice.

    One statement each, inside the caller's transaction, so a profile is never
    left holding half a CV's skills.
    """
    selected = resolver if resolver is not None else load_default_resolver()
    concepts = concepts_in(text, selected)

    await session.execute(
        delete(CandidateProfileSkill).where(
            CandidateProfileSkill.profile_id == profile_id,
            CandidateProfileSkill.source == SkillSource.CV,
        )
    )
    if not concepts:
        return ExtractedCVSkills(
            vocabulary_version=selected.vocabulary_version, added=(), already_chosen=()
        )

    written = await session.scalars(
        insert(CandidateProfileSkill)
        .values(
            [
                {
                    "profile_id": profile_id,
                    "concept_id": concept,
                    "vocabulary_version": selected.vocabulary_version,
                    "source": SkillSource.CV,
                }
                for concept in concepts
            ]
        )
        .on_conflict_do_nothing(index_elements=["profile_id", "concept_id"])
        .returning(CandidateProfileSkill.concept_id)
    )
    added = frozenset(written)

    return ExtractedCVSkills(
        vocabulary_version=selected.vocabulary_version,
        added=tuple(concept for concept in concepts if concept in added),
        already_chosen=tuple(concept for concept in concepts if concept not in added),
    )
