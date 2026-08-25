"""Publish a validated alias-table artifact to PostgreSQL."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.skills.models import SkillAliasVersion, SkillConcept, SkillSurfaceForm
from app.modules.skills.resolution import AliasTableDocument, load_resolver, normalize_surface_form

ConceptContent = tuple[str, str | None]
SurfaceFormContent = tuple[str, str, UUID]


class PublishedAliasConflictError(RuntimeError):
    """Stored content disagrees with an immutable alias publication."""


@dataclass(frozen=True, slots=True)
class AliasTableLoadResult:
    """The rows created by one load attempt."""

    vocabulary_version: str
    loaded: bool
    concepts_inserted: int
    surface_forms_inserted: int


def _expected_concepts(document: AliasTableDocument) -> dict[UUID, ConceptContent]:
    return {
        concept.id: (concept.preferred_label, concept.esco_uri) for concept in document.concepts
    }


def _expected_surface_forms(document: AliasTableDocument) -> set[SurfaceFormContent]:
    return {
        (
            entry.surface_form,
            normalize_surface_form(entry.surface_form),
            concept_id,
        )
        for entry in document.surface_forms
        for concept_id in entry.concept_ids
    }


def _concept_difference(
    expected: dict[UUID, ConceptContent],
    stored: dict[UUID, SkillConcept],
    *,
    missing_is_difference: bool,
) -> str | None:
    for concept_id in sorted(expected, key=str):
        concept = stored.get(concept_id)
        if concept is None:
            if missing_is_difference:
                return f"concept {concept_id} is missing"
            continue

        expected_label, expected_esco_uri = expected[concept_id]
        if concept.preferred_label != expected_label:
            return (
                f"concept {concept_id} preferred_label differs "
                f"(stored {concept.preferred_label!r}, artifact {expected_label!r})"
            )
        if concept.esco_uri != expected_esco_uri:
            return (
                f"concept {concept_id} esco_uri differs "
                f"(stored {concept.esco_uri!r}, artifact {expected_esco_uri!r})"
            )
    return None


def _format_surface_form(content: SurfaceFormContent) -> str:
    surface_form, normalized_form, concept_id = content
    return (
        f"surface_form={surface_form!r}, normalized_form={normalized_form!r}, "
        f"concept_id={concept_id}"
    )


def _surface_form_sort_key(content: SurfaceFormContent) -> tuple[str, str, str]:
    return content[0], content[1], str(content[2])


def _surface_form_difference(
    expected: set[SurfaceFormContent], stored: set[SurfaceFormContent]
) -> str | None:
    missing = sorted(expected - stored, key=_surface_form_sort_key)
    if missing:
        return f"surface-form row is missing ({_format_surface_form(missing[0])})"

    unexpected = sorted(stored - expected, key=_surface_form_sort_key)
    if unexpected:
        return f"surface-form row is unexpected ({_format_surface_form(unexpected[0])})"
    return None


async def load_published_alias_table(
    session: AsyncSession,
    vocabulary_version: str,
) -> AliasTableLoadResult:
    """Insert one published version, or verify that its stored copy is identical.

    The caller owns the transaction. This function flushes new rows so a
    successful result means all constraints accepted the publication, but it
    never commits independently.
    """
    document = load_resolver(vocabulary_version).document
    expected_concepts = _expected_concepts(document)
    expected_surface_forms = _expected_surface_forms(document)

    version = await session.get(SkillAliasVersion, vocabulary_version)
    stored_concepts = {
        concept.id: concept
        for concept in await session.scalars(
            select(SkillConcept).where(SkillConcept.id.in_(expected_concepts))
        )
    }
    concept_difference = _concept_difference(
        expected_concepts,
        stored_concepts,
        missing_is_difference=version is not None,
    )

    if version is not None:
        if concept_difference is not None:
            raise PublishedAliasConflictError(
                f"published alias version {vocabulary_version} differs from its artifact: "
                f"{concept_difference}"
            )

        stored_surface_forms = {
            (surface_form, normalized_form, concept_id)
            for surface_form, normalized_form, concept_id in (
                await session.execute(
                    select(
                        SkillSurfaceForm.surface_form,
                        SkillSurfaceForm.normalized_form,
                        SkillSurfaceForm.concept_id,
                    ).where(SkillSurfaceForm.alias_version == vocabulary_version)
                )
            ).all()
        }
        surface_form_difference = _surface_form_difference(
            expected_surface_forms, stored_surface_forms
        )
        if surface_form_difference is not None:
            raise PublishedAliasConflictError(
                f"published alias version {vocabulary_version} differs from its artifact: "
                f"{surface_form_difference}"
            )
        return AliasTableLoadResult(
            vocabulary_version=vocabulary_version,
            loaded=False,
            concepts_inserted=0,
            surface_forms_inserted=0,
        )

    if concept_difference is not None:
        raise PublishedAliasConflictError(
            f"alias version {vocabulary_version} cannot be loaded: {concept_difference}"
        )

    missing_concepts = [
        SkillConcept(
            id=concept.id,
            preferred_label=concept.preferred_label,
            esco_uri=concept.esco_uri,
        )
        for concept in document.concepts
        if concept.id not in stored_concepts
    ]
    session.add_all([*missing_concepts, SkillAliasVersion(version=vocabulary_version)])
    await session.flush()

    session.add_all(
        [
            SkillSurfaceForm(
                alias_version=vocabulary_version,
                concept_id=concept_id,
                surface_form=surface_form,
                normalized_form=normalized_form,
            )
            for surface_form, normalized_form, concept_id in expected_surface_forms
        ]
    )
    await session.flush()
    return AliasTableLoadResult(
        vocabulary_version=vocabulary_version,
        loaded=True,
        concepts_inserted=len(missing_concepts),
        surface_forms_inserted=len(expected_surface_forms),
    )
