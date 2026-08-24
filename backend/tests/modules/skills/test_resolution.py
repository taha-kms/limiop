from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.skills.resolution import (
    AliasTableDocument,
    KnownSkillResolver,
    ResolutionStatus,
    load_default_resolver,
    normalize_surface_form,
)


@pytest.fixture(scope="module")
def resolver() -> KnownSkillResolver:
    return load_default_resolver()


def test_alias_table_has_an_explicit_version(resolver: KnownSkillResolver) -> None:
    assert resolver.vocabulary_version == "2026.08.24.1"


@pytest.mark.parametrize("term", ["postgres", "POSTGRES", "  Postgres!  "])
def test_casing_and_surrounding_punctuation_resolve_to_one_concept(
    resolver: KnownSkillResolver, term: str
) -> None:
    result = resolver.resolve(term)

    assert result.status is ResolutionStatus.RESOLVED
    assert result.concepts[0].preferred_label == "PostgreSQL"
    assert result.vocabulary_version == resolver.vocabulary_version


def test_meaningful_programming_language_punctuation_is_preserved(
    resolver: KnownSkillResolver,
) -> None:
    assert resolver.resolve("C#").concepts[0].preferred_label == "C#"
    assert normalize_surface_form("C++") == "c++"
    assert resolver.resolve("C++").status is ResolutionStatus.UNMAPPED


def test_separator_and_orthographic_variants_are_explicit_aliases(
    resolver: KnownSkillResolver,
) -> None:
    punctuated = resolver.resolve("product-demo")
    american = resolver.resolve("organizational skills")
    british = resolver.resolve("organisational skills")

    assert punctuated.concepts[0].preferred_label == "Product demonstration"
    assert american.concepts[0].id == british.concepts[0].id


def test_different_labels_resolve_to_the_same_stable_identity(
    resolver: KnownSkillResolver,
) -> None:
    noun = resolver.resolve("product demonstration")
    plural = resolver.resolve("product demos")

    assert noun.status is ResolutionStatus.RESOLVED
    assert noun.concepts[0].id == plural.concepts[0].id


def test_an_ambiguous_alias_returns_every_candidate_in_stable_order(
    resolver: KnownSkillResolver,
) -> None:
    first = resolver.resolve("AI")
    second = resolver.resolve("ai")

    assert first.status is ResolutionStatus.AMBIGUOUS
    assert first == second
    assert [str(concept.id) for concept in first.concepts] == sorted(
        str(concept.id) for concept in first.concepts
    )
    assert {concept.preferred_label for concept in first.concepts} == {
        "Adobe Illustrator",
        "Artificial intelligence",
    }


def test_an_unmapped_term_is_not_guessed_or_created(resolver: KnownSkillResolver) -> None:
    result = resolver.resolve("quantum widget orchestration")

    assert result.status is ResolutionStatus.UNMAPPED
    assert result.concepts == ()


@pytest.mark.parametrize("term", ["own", "projects", "testing", "engineering"])
def test_known_broad_false_positives_remain_unmapped(
    resolver: KnownSkillResolver, term: str
) -> None:
    assert resolver.resolve(term).status is ResolutionStatus.UNMAPPED


def test_esco_mapping_is_optional_per_concept() -> None:
    concept_without_mapping = {
        "id": "8cb94723-c872-47d2-883b-cb7c4201849b",
        "preferred_label": "Unmapped concept",
    }
    concept_with_mapping = {
        "id": "a487a42c-feba-42ef-bcbd-a793f0188627",
        "preferred_label": "Mapped concept",
        "esco_uri": "https://data.europa.eu/esco/skill/example",
    }
    document = AliasTableDocument.model_validate(
        {
            "schema_version": 1,
            "vocabulary_version": "test.1",
            "concepts": [concept_without_mapping, concept_with_mapping],
            "surface_forms": [
                {
                    "surface_form": "unmapped concept",
                    "concept_ids": [concept_without_mapping["id"]],
                },
                {
                    "surface_form": "mapped concept",
                    "concept_ids": [concept_with_mapping["id"]],
                },
            ],
        }
    )

    assert document.concepts[0].esco_uri is None
    assert document.concepts[1].esco_uri == "https://data.europa.eu/esco/skill/example"


def test_alias_data_cannot_reference_a_missing_concept() -> None:
    with pytest.raises(ValidationError, match="references unknown concepts"):
        AliasTableDocument.model_validate(
            {
                "schema_version": 1,
                "vocabulary_version": "test.1",
                "concepts": [
                    {
                        "id": "8cb94723-c872-47d2-883b-cb7c4201849b",
                        "preferred_label": "Known concept",
                    }
                ],
                "surface_forms": [
                    {
                        "surface_form": "missing",
                        "concept_ids": ["b628ff48-9ed3-426d-8d3f-a17f18b71f50"],
                    }
                ],
            }
        )


def test_normalization_collisions_must_be_one_reviewable_alias_row() -> None:
    concept_id = UUID("8cb94723-c872-47d2-883b-cb7c4201849b")
    with pytest.raises(ValidationError, match="duplicated after normalization"):
        AliasTableDocument.model_validate(
            {
                "schema_version": 1,
                "vocabulary_version": "test.1",
                "concepts": [{"id": concept_id, "preferred_label": "Product demonstration"}],
                "surface_forms": [
                    {"surface_form": "product demo", "concept_ids": [concept_id]},
                    {"surface_form": "product-demo", "concept_ids": [concept_id]},
                ],
            }
        )
