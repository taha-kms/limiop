from datetime import UTC, datetime
from typing import Any

import pytest

from app.modules.jobs.fingerprint import (
    FINGERPRINT_VERSION,
    fingerprint,
    fingerprint_parts,
    normalize_title,
)
from app.modules.jobs.schemas import NormalizedJob


def job(**overrides: Any) -> NormalizedJob:
    payload: dict[str, Any] = {
        "company": {"display_name": "Acme GmbH"},
        "title": "Senior Data Engineer",
        "description": "Build reliable data pipelines.",
        "location": "Berlin",
        "application_url": "https://acme.example.com/jobs/data-engineer",
        "published_at": datetime(2026, 8, 18, 10, tzinfo=UTC),
        "provenance": {
            "source_key": "arbeitnow",
            "source_job_id": "external-42",
            "source_url": "https://arbeitnow.example.com/jobs/42",
        },
    }
    payload.update(overrides)
    return NormalizedJob.model_validate(payload)


def test_a_fingerprint_is_versioned() -> None:
    value = fingerprint(job())

    assert value.startswith(f"{FINGERPRINT_VERSION}:")
    assert len(value.removeprefix(f"{FINGERPRINT_VERSION}:")) == 64


def test_the_same_job_fingerprints_the_same_way() -> None:
    first = fingerprint(job())
    second = fingerprint(job())

    assert first == second


@pytest.mark.parametrize(
    "overrides",
    [
        {"company": {"display_name": "ACME  gmbh"}},
        {"title": "  senior   DATA engineer "},
        {"location": "  berlin "},
        {"title": "Senior Data Engineer (m/w/d)"},
        {"title": "Senior Data Engineer (m/f/d)"},
        {"title": "Senior Data Engineer (M/W/D)"},
        {"title": "Senior Data Engineer (all genders)"},
        {"title": "Senior Data Engineer (m|w|d)"},
    ],
    ids=[
        "company casing and spacing",
        "title casing and spacing",
        "location casing and spacing",
        "german gender notation",
        "english gender notation",
        "uppercase gender notation",
        "all genders notation",
        "pipe separated notation",
    ],
)
def test_cosmetic_differences_do_not_change_the_fingerprint(overrides: dict[str, Any]) -> None:
    assert fingerprint(job(**overrides)) == fingerprint(job())


@pytest.mark.parametrize(
    "overrides",
    [
        {"company": {"display_name": "Beispiel AG"}},
        {"title": "Junior Data Engineer"},
        {"title": "Senior Data Engineer II"},
        {"location": "Munich"},
        {"location": None},
    ],
    ids=[
        "different company",
        "different seniority",
        "different level suffix",
        "different city",
        "no location",
    ],
)
def test_material_differences_change_the_fingerprint(overrides: dict[str, Any]) -> None:
    assert fingerprint(job(**overrides)) != fingerprint(job())


def test_fields_that_change_without_a_new_posting_are_excluded() -> None:
    reworded = job(
        description="We are hiring! Build reliable data pipelines. Apply today.",
        application_url="https://acme.example.com/careers/12345",
        published_at=datetime(2026, 12, 1, tzinfo=UTC),
        provenance={
            "source_key": "jobicy",
            "source_job_id": "different-id",
            "source_url": "https://jobicy.example.com/jobs/999",
        },
    )

    assert fingerprint(reworded) == fingerprint(job())


def test_the_same_posting_from_two_providers_matches() -> None:
    from_arbeitnow = job(
        application_url="https://www.arbeitnow.com/jobs/acme-senior-data-engineer",
        provenance={
            "source_key": "arbeitnow",
            "source_job_id": "acme-senior-data-engineer",
            "source_url": "https://www.arbeitnow.com/jobs/acme-senior-data-engineer",
        },
    )
    from_jobicy = job(
        title="Senior Data Engineer (m/w/d)",
        application_url="https://jobicy.com/jobs/98765",
        provenance={
            "source_key": "jobicy",
            "source_job_id": "98765",
            "source_url": "https://jobicy.com/jobs/98765",
        },
    )

    assert fingerprint(from_arbeitnow) == fingerprint(from_jobicy)


def test_the_computed_parts_are_inspectable() -> None:
    assert fingerprint_parts(job()) == ("acme gmbh", "senior data engineer", "berlin")


def test_a_job_without_a_location_uses_an_empty_part() -> None:
    assert fingerprint_parts(job(location=None)) == ("acme gmbh", "senior data engineer", "")


def test_part_boundaries_cannot_be_shifted_between_fields() -> None:
    shifted = job(company={"display_name": "Acme"}, title="GmbH Senior Data Engineer")

    assert fingerprint(shifted) != fingerprint(job())


def test_unicode_forms_of_the_same_name_agree() -> None:
    composed = job(company={"display_name": "Café AG"})
    decomposed = job(company={"display_name": "Café AG"})

    assert composed.company.display_name != decomposed.company.display_name
    assert fingerprint(composed) == fingerprint(decomposed)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Data Engineer (m/w/d)", "data engineer"),
        ("Data Engineer (w/m/d)", "data engineer"),
        ("Data Engineer (m/w/x)", "data engineer"),
        ("Data Engineer (all gender)", "data engineer"),
        ("Data Engineer (Remote)", "data engineer (remote)"),
        ("Data Engineer (Berlin)", "data engineer (berlin)"),
        ("Data Engineer", "data engineer"),
    ],
)
def test_only_gender_notation_is_stripped_from_a_title(title: str, expected: str) -> None:
    assert normalize_title(title) == expected
