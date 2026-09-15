import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from platform_db.models.catalog import EmploymentType, WorkplaceType

from job_ingestion.errors import RecordValidationError
from job_ingestion.himalayas.normalizer import HimalayasNormalizer, to_employment_type
from job_ingestion.himalayas.records import HimalayasValidator
from job_ingestion.schemas import NormalizedJob

FIXTURES = Path(__file__).parent / "fixtures"


def page_records(name: str = "page_one.json") -> list[dict[str, Any]]:
    body = json.loads((FIXTURES / name).read_text())
    records: list[dict[str, Any]] = body["jobs"]
    return records


def raw_record(**overrides: Any) -> dict[str, Any]:
    record = page_records()[0].copy()
    record.update(overrides)
    return record


def normalize(**overrides: Any) -> NormalizedJob:
    raw = raw_record(**overrides)
    return HimalayasNormalizer().normalize(HimalayasValidator().validate(raw), raw)


def test_a_representative_record_becomes_a_canonical_job() -> None:
    job = normalize()

    assert job.title == "Director, Value Attainment & Analysis"
    assert job.company.display_name == "abridge"
    assert job.location == "United States"
    assert job.workplace_type is WorkplaceType.REMOTE
    assert job.employment_type is EmploymentType.FULL_TIME
    assert str(job.application_url).endswith("director-value-attainment-analysis")
    assert job.published_at == datetime.fromtimestamp(1789465009, UTC)
    assert job.expires_at == datetime.fromtimestamp(1794649007, UTC)


def test_normalization_is_deterministic() -> None:
    raw = raw_record()
    record = HimalayasValidator().validate(raw)
    normalizer = HimalayasNormalizer()

    first = normalizer.normalize(record, raw)
    second = normalizer.normalize(record, raw)

    assert first == second


def test_provenance_identifies_the_external_record() -> None:
    raw = raw_record()
    job = normalize()

    assert job.provenance.source_key == "himalayas"
    assert job.provenance.source_job_id == raw["guid"]
    assert str(job.provenance.source_url) == raw["guid"]


def test_provenance_preserves_fields_that_validation_ignored() -> None:
    job = normalize()

    assert job.provenance.raw_payload is not None
    assert job.provenance.raw_payload["companySlug"] == "abridge"


def test_html_is_reduced_to_plain_text() -> None:
    job = normalize()

    assert "<" not in job.description
    assert job.description.startswith("About Abridge")


def test_a_description_of_only_markup_is_rejected() -> None:
    with pytest.raises(RecordValidationError, match="description"):
        normalize(description="<div><span></span></div>")


def test_a_rejected_record_is_still_identifiable() -> None:
    with pytest.raises(RecordValidationError) as error:
        normalize(description="<br>")

    assert error.value.source_job_id == raw_record()["guid"]
    assert error.value.source_key == "himalayas"


@pytest.mark.parametrize(
    ("employment_type", "expected"),
    [
        ("Full Time", EmploymentType.FULL_TIME),
        ("Part Time", EmploymentType.PART_TIME),
        ("Contract", EmploymentType.CONTRACT),
        ("Freelance", EmploymentType.CONTRACT),
        ("Internship", EmploymentType.INTERNSHIP),
        ("Temporary", EmploymentType.TEMPORARY),
        ("", EmploymentType.UNSPECIFIED),
        ("Volunteer", EmploymentType.UNSPECIFIED),
    ],
)
def test_employment_type_prefers_the_most_specific_signal(
    employment_type: str,
    expected: EmploymentType,
) -> None:
    assert to_employment_type(employment_type) is expected


def test_the_workplace_is_always_remote() -> None:
    """Himalayas is a remote-only board: every posting is remote by definition,
    whatever its own fields happen to say about location."""
    assert normalize(locationRestrictions=["Germany"]).workplace_type is WorkplaceType.REMOTE
    assert normalize(locationRestrictions=[]).workplace_type is WorkplaceType.REMOTE


def test_location_joins_every_restriction() -> None:
    job = normalize(locationRestrictions=["United States", "Canada"])

    assert job.location == "United States, Canada"


def test_no_location_restrictions_leaves_the_location_absent() -> None:
    job = normalize(locationRestrictions=[])

    assert job.location is None


def test_a_record_without_a_pub_date_has_no_publication_date() -> None:
    record = raw_record()
    del record["pubDate"]

    job = HimalayasNormalizer().normalize(HimalayasValidator().validate(record), record)

    assert job.published_at is None


def test_a_record_without_an_expiry_date_has_no_expiration_date() -> None:
    record = raw_record()
    del record["expiryDate"]

    job = HimalayasNormalizer().normalize(HimalayasValidator().validate(record), record)

    assert job.expires_at is None


def test_expiry_before_publication_drops_the_expiry_but_keeps_the_record() -> None:
    """The canonical contract refuses expiry before publication; a feed glitch
    should not lose the posting over it."""
    job = normalize(pubDate=1000, expiryDate=500)

    assert job.published_at == datetime.fromtimestamp(1000, UTC)
    assert job.expires_at is None


def test_expiry_without_publication_is_kept() -> None:
    record = raw_record(expiryDate=500)
    del record["pubDate"]

    job = HimalayasNormalizer().normalize(HimalayasValidator().validate(record), record)

    assert job.published_at is None
    assert job.expires_at == datetime.fromtimestamp(500, UTC)


def test_the_second_fixture_record_normalizes_too() -> None:
    raw = page_records()[1]
    job = HimalayasNormalizer().normalize(HimalayasValidator().validate(raw), raw)

    assert job.title == "Senior Software Engineer, Partnerships & Integrations (Open-Source)"
    assert job.company.display_name == "CopilotKit"
    assert job.workplace_type is WorkplaceType.REMOTE
    assert job.employment_type is EmploymentType.FULL_TIME


def test_the_canonical_job_carries_no_provider_specific_fields() -> None:
    job = normalize()

    assert "categories" not in job.model_dump()
    assert "seniority" not in job.model_dump()
    assert "guid" not in job.model_dump()
