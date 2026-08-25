import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.skills import TEXT_MATCHING_HAZARD_FORMS
from app.modules.skills.resolution import (
    DEFAULT_VOCABULARY_VERSION,
    PUBLISHED_ALIAS_TABLES,
    AliasTableDocument,
    KnownSkillResolver,
    ResolutionStatus,
    load_default_resolver,
    load_resolver,
    normalize_surface_form,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def resolver() -> KnownSkillResolver:
    return load_resolver("2026.08.24.1")


def test_alias_table_has_an_explicit_version(resolver: KnownSkillResolver) -> None:
    assert resolver.vocabulary_version == "2026.08.24.1"


def test_newest_alias_table_is_the_default() -> None:
    resolver = load_default_resolver()

    assert resolver.vocabulary_version == DEFAULT_VOCABULARY_VERSION == "2026.08.25.1"
    assert resolver.resolve("machine learning").concepts[0].preferred_label == "Machine learning"


@pytest.mark.parametrize(
    ("version", "term", "preferred_label"),
    [
        ("2026.08.24.1", "Postgres", "PostgreSQL"),
        ("2026.08.25.1", "deep learning", "Machine learning"),
    ],
)
def test_every_published_alias_table_loads_and_resolves(
    version: str, term: str, preferred_label: str
) -> None:
    result = load_resolver(version).resolve(term)

    assert result.status is ResolutionStatus.RESOLVED
    assert result.concepts[0].preferred_label == preferred_label
    assert set(PUBLISHED_ALIAS_TABLES) == {"2026.08.24.1", "2026.08.25.1"}


def test_unpublished_alias_table_version_fails_loudly() -> None:
    with pytest.raises(ValueError, match=r"alias table version is not published: 2099\.01\.01\.1"):
        load_resolver("2099.01.01.1")


def test_v2_matches_the_frozen_curated_arm_exactly_after_normalization() -> None:
    curated = json.loads(
        (REPOSITORY_ROOT / "docs/skill-model-measurement/in-progress/curated-arm.json").read_text(
            encoding="utf-8"
        )
    )
    artifact = json.loads(
        (REPOSITORY_ROOT / "backend/app/modules/skills/data/aliases.v2.json").read_text(
            encoding="utf-8"
        )
    )

    expected_by_form: dict[str, tuple[str, str]] = {}
    raw_forms = 0
    for entry in curated["entries"]:
        for alias in entry["aliases"]:
            raw_forms += 1
            expected_by_form.setdefault(normalize_surface_form(alias), (alias, entry["label"]))

    concept_labels = {concept["id"]: concept["preferred_label"] for concept in artifact["concepts"]}
    published_by_form = {
        normalize_surface_form(form["surface_form"]): (
            form["surface_form"],
            concept_labels[form["concept_ids"][0]].lower(),
        )
        for form in artifact["surface_forms"]
    }

    assert artifact["schema_version"] == 1
    assert artifact["vocabulary_version"] == "2026.08.25.1"
    assert len(artifact["concepts"]) == len(curated["entries"]) == 56
    assert len({concept["id"] for concept in artifact["concepts"]}) == 56
    assert all("esco_uri" not in concept for concept in artifact["concepts"])
    assert [concept["preferred_label"] for concept in artifact["concepts"]] == [
        entry["label"][0].upper() + entry["label"][1:] for entry in curated["entries"]
    ]
    assert raw_forms == 184
    assert len(artifact["surface_forms"]) == len(expected_by_form) == 182
    assert published_by_form == expected_by_form


def test_text_matching_hazards_are_importable_and_published() -> None:
    assert TEXT_MATCHING_HAZARD_FORMS == (
        "ai",
        "aws",
        "b2b",
        "gcp",
        "gpu",
        "ml",
        "own",
        "qa",
        "ux",
    )
    assert all(
        load_default_resolver().resolve(term).status is ResolutionStatus.RESOLVED
        for term in TEXT_MATCHING_HAZARD_FORMS
    )


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
def test_v1_does_not_infer_unpublished_terms(resolver: KnownSkillResolver, term: str) -> None:
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
