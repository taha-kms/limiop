from datetime import UTC, datetime
from typing import Any

import pytest
from platform_db.models.catalog import EmploymentType, WorkplaceType

from job_ingestion.adzuna.normalizer import AdzunaNormalizer, to_employment_type
from job_ingestion.adzuna.records import AdzunaValidator
from job_ingestion.errors import RecordValidationError
from job_ingestion.schemas import NormalizedJob
from tests.adzuna.support import page_records, posting


def normalize(**overrides: Any) -> NormalizedJob:
    raw = posting(**overrides)
    return AdzunaNormalizer().normalize(AdzunaValidator().validate(raw), raw)


def test_a_representative_record_becomes_a_canonical_job() -> None:
    job = normalize()

    assert job.company.display_name == "Northwind Analytics"
    assert job.title == "Senior Data Engineer"
    assert job.description.startswith("We are looking for a Senior Data Engineer")
    assert job.location == "London, UK"
    assert job.workplace_type is WorkplaceType.UNSPECIFIED
    assert job.employment_type is EmploymentType.FULL_TIME
    assert str(job.application_url) == posting()["redirect_url"]
    assert job.published_at == datetime(2026, 9, 14, 8, 15, 22, tzinfo=UTC)
    assert job.expires_at is None


def test_normalization_is_deterministic() -> None:
    raw = posting()
    record = AdzunaValidator().validate(raw)
    normalizer = AdzunaNormalizer()

    first = normalizer.normalize(record, raw)
    second = normalizer.normalize(record, raw)

    assert first == second


def test_provenance_identifies_the_record_within_its_country() -> None:
    raw = posting()
    job = normalize()

    assert job.provenance.source_key == "adzuna"
    assert job.provenance.source_job_id == "gb:5312407781"
    assert str(job.provenance.source_url) == raw["redirect_url"]


def test_the_same_id_in_another_country_is_another_record() -> None:
    assert normalize(country="de").provenance.source_job_id == "de:5312407781"


def test_the_snippet_is_flagged_as_a_partial_description() -> None:
    """Adzuna serves an excerpt, never the posting: the flag is what keeps
    deduplication from ever comparing it by text."""
    assert normalize().provenance.partial_description is True


def test_provenance_preserves_fields_that_validation_ignored() -> None:
    job = normalize()

    assert job.provenance.raw_payload is not None
    assert job.provenance.raw_payload["adref"] == posting()["adref"]
    assert job.provenance.raw_payload["country"] == "gb"


def test_markup_in_the_snippet_is_reduced_to_plain_text() -> None:
    job = normalize(description="<p>We build <strong>pipelines</strong> …</p>")

    assert job.description == "We build pipelines …"


def test_a_snippet_of_only_markup_is_rejected() -> None:
    with pytest.raises(RecordValidationError, match="description") as error:
        normalize(description="<div><span></span></div>")

    assert error.value.source_job_id == "gb:5312407781"
    assert error.value.source_key == "adzuna"


@pytest.mark.parametrize(
    ("contract_time", "contract_type", "expected"),
    [
        ("full_time", "permanent", EmploymentType.FULL_TIME),
        ("full_time", "", EmploymentType.FULL_TIME),
        ("part_time", "", EmploymentType.PART_TIME),
        ("part_time", "permanent", EmploymentType.PART_TIME),
        ("", "contract", EmploymentType.CONTRACT),
        ("full_time", "contract", EmploymentType.CONTRACT),
        ("", "permanent", EmploymentType.UNSPECIFIED),
        ("", "", EmploymentType.UNSPECIFIED),
    ],
)
def test_employment_type_reads_both_contract_fields(
    contract_time: str, contract_type: str, expected: EmploymentType
) -> None:
    assert to_employment_type(contract_time, contract_type) is expected


def test_the_workplace_is_never_inferred() -> None:
    """Adzuna states nothing about where the work happens, and a word in the
    snippet is not a statement of it: `Remote Sensing Engineer` is a job."""
    job = normalize(
        title="Remote Sensing Engineer", description="Fully remote role, work from home."
    )

    assert job.workplace_type is WorkplaceType.UNSPECIFIED


def test_a_blank_location_leaves_the_place_absent() -> None:
    assert normalize(location={"display_name": "", "area": []}).location is None
    assert normalize(location={"display_name": "   "}).location is None


def test_a_record_without_a_created_date_has_no_publication_date() -> None:
    raw = posting()
    del raw["created"]

    job = AdzunaNormalizer().normalize(AdzunaValidator().validate(raw), raw)

    assert job.published_at is None


def test_a_german_record_keeps_its_gender_notation_in_the_title() -> None:
    raw = page_records("de")[0]
    job = AdzunaNormalizer().normalize(AdzunaValidator().validate(raw), raw)

    assert job.title == "Data Engineer (m/w/d)"
    assert job.company.display_name == "Bergmann Software GmbH"
    assert job.location == "Berlin, Berlin"
    assert job.provenance.source_job_id == "de:5311980427"


@pytest.mark.parametrize("country", ["gb", "de"])
def test_every_fixture_record_normalizes(country: str) -> None:
    validator, normalizer = AdzunaValidator(), AdzunaNormalizer()

    jobs = [normalizer.normalize(validator.validate(raw), raw) for raw in page_records(country)]

    assert len({job.provenance.source_job_id for job in jobs}) == 3
    assert all(job.provenance.partial_description for job in jobs)


def test_the_canonical_job_carries_no_provider_specific_fields() -> None:
    dumped = normalize().model_dump()

    assert "adref" not in dumped
    assert "category" not in dumped
    assert "salary_min" not in dumped
