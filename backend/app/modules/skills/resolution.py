"""Deterministic resolution of terms already present in the alias table.

This module deliberately ends at ``UNMAPPED``. Deciding whether an unmapped
term is a legitimate skill belongs to the later unknown-skill gate.
"""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from importlib import resources
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyLabel = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
NonEmptyVersion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
]

_SEPARATORS = re.compile(r"[\s_\-\u2010-\u2015]+")
_SURROUNDING_PUNCTUATION = " \t\r\n.,;:!?()[]{}\"'"


def normalize_surface_form(value: str) -> str:
    """Return the conservative lookup form shared by data and callers.

    Unicode compatibility normalization, case folding, separator folding, and
    surrounding prose punctuation are safe equivalences. Meaningful symbols
    such as ``#`` and ``+`` remain, so C, C#, and C++ do not collapse.
    """
    compatible = unicodedata.normalize("NFKC", value).casefold()
    unpunctuated = compatible.strip(_SURROUNDING_PUNCTUATION)
    return _SEPARATORS.sub(" ", unpunctuated).strip()


class SkillConceptDefinition(BaseModel):
    """A concept as published in an alias-table artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    preferred_label: NonEmptyLabel
    esco_uri: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
        ]
        | None
    ) = None


class SurfaceFormDefinition(BaseModel):
    """One lookup form and every concept it can mean."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    surface_form: NonEmptyLabel
    concept_ids: tuple[UUID, ...] = Field(min_length=1)


class AliasTableDocument(BaseModel):
    """The checked-in, versioned data contract for known skills."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    vocabulary_version: NonEmptyVersion
    concepts: tuple[SkillConceptDefinition, ...] = Field(min_length=1)
    surface_forms: tuple[SurfaceFormDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references_and_uniqueness(self) -> Self:
        concept_ids = [concept.id for concept in self.concepts]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("concept ids must be unique")

        known_ids = set(concept_ids)
        normalized_forms: set[str] = set()
        for entry in self.surface_forms:
            normalized = normalize_surface_form(entry.surface_form)
            if not normalized:
                raise ValueError("surface forms must contain a term")
            if normalized in normalized_forms:
                raise ValueError(f"surface form is duplicated after normalization: {normalized}")
            normalized_forms.add(normalized)

            referenced_ids = set(entry.concept_ids)
            if len(referenced_ids) != len(entry.concept_ids):
                raise ValueError(f"surface form repeats a concept: {entry.surface_form}")
            missing = referenced_ids - known_ids
            if missing:
                raise ValueError(f"surface form references unknown concepts: {sorted(missing)}")
        return self


class ResolutionStatus(StrEnum):
    """Every possible outcome of known-skill resolution."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNMAPPED = "unmapped"


@dataclass(frozen=True, slots=True)
class SkillResolution:
    """The explicit result of resolving one surface term."""

    status: ResolutionStatus
    normalized_term: str
    concepts: tuple[SkillConceptDefinition, ...]
    vocabulary_version: str


class KnownSkillResolver:
    """Resolve only terms published by one immutable alias-table version."""

    def __init__(self, document: AliasTableDocument) -> None:
        self._version = document.vocabulary_version
        self._concepts: Mapping[UUID, SkillConceptDefinition] = {
            concept.id: concept for concept in document.concepts
        }
        self._concept_ids_by_form: Mapping[str, tuple[UUID, ...]] = {
            normalize_surface_form(entry.surface_form): tuple(sorted(entry.concept_ids, key=str))
            for entry in document.surface_forms
        }

    @property
    def vocabulary_version(self) -> str:
        return self._version

    def resolve(self, term: str) -> SkillResolution:
        normalized = normalize_surface_form(term)
        concept_ids = self._concept_ids_by_form.get(normalized, ())
        concepts = tuple(self._concepts[concept_id] for concept_id in concept_ids)
        if len(concepts) == 1:
            status = ResolutionStatus.RESOLVED
        elif concepts:
            status = ResolutionStatus.AMBIGUOUS
        else:
            status = ResolutionStatus.UNMAPPED
        return SkillResolution(
            status=status,
            normalized_term=normalized,
            concepts=concepts,
            vocabulary_version=self._version,
        )


@lru_cache(maxsize=1)
def load_default_resolver() -> KnownSkillResolver:
    """Load the alias artifact shipped with this backend package."""
    payload = (
        resources.files("app.modules.skills")
        .joinpath("data/aliases.v1.json")
        .read_text(encoding="utf-8")
    )
    return KnownSkillResolver(AliasTableDocument.model_validate_json(payload))
