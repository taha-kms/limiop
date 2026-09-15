import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from platform_db.models.catalog import EmploymentType, WorkplaceType

from job_ingestion.errors import RecordValidationError
from job_ingestion.jobicy.normalizer import JobicyNormalizer, to_location
from job_ingestion.jobicy.records import JobicyValidator
from job_ingestion.schemas import NormalizedJob

FIXTURES = Path(__file__).parent / "fixtures"


def feed_jobs() -> list[dict[str, Any]]:
    body = json.loads((FIXTURES / "remote_jobs.json").read_text())
    jobs: list[dict[str, Any]] = body["jobs"]
    return jobs


def raw_job(**overrides: Any) -> dict[str, Any]:
    record = feed_jobs()[0].copy()
    record.update(overrides)
    return record


def normalize(**overrides: Any) -> NormalizedJob:
    raw = raw_job(**overrides)
    return JobicyNormalizer().normalize(JobicyValidator().validate(raw), raw)


def test_a_representative_record_becomes_a_canonical_job() -> None:
    job = normalize()

    assert job.title == "SVP, Product"
    assert job.company.display_name == "Toptal"
    assert job.location == "Canada, Europe"
    assert job.workplace_type is WorkplaceType.REMOTE
    assert job.employment_type is EmploymentType.FULL_TIME
    assert str(job.application_url) == "https://jobicy.com/jobs/153312-svp-product"
    assert job.published_at == datetime(2026, 9, 15, 6, 3, 2, tzinfo=UTC)
    assert job.expires_at is None


def test_normalization_is_deterministic() -> None:
    raw = raw_job()
    record = JobicyValidator().validate(raw)
    normalizer = JobicyNormalizer()

    first = normalizer.normalize(record, raw)
    second = normalizer.normalize(record, raw)

    assert first == second


def test_workplace_is_always_remote_regardless_of_geography() -> None:
    """The feed is remote-only by definition; nothing states otherwise."""
    assert normalize(jobGeo="Germany").workplace_type is WorkplaceType.REMOTE
    assert normalize(jobGeo="").workplace_type is WorkplaceType.REMOTE
    assert normalize(jobGeo="Anywhere").workplace_type is WorkplaceType.REMOTE


def test_provenance_identifies_the_external_record() -> None:
    job = normalize()

    assert job.provenance.source_key == "jobicy"
    assert job.provenance.source_job_id == "153312"
    assert str(job.provenance.source_url) == str(job.application_url)


def test_provenance_preserves_the_feeds_own_identifier_type() -> None:
    """The raw payload keeps the numeric `id` the feed actually sent."""
    job = normalize()

    assert job.provenance.raw_payload is not None
    assert job.provenance.raw_payload["id"] == 153312


def test_html_is_reduced_to_plain_text() -> None:
    job = normalize(jobDescription="<p>Build reliable data pipelines.</p><p>Python</p>")

    assert "<" not in job.description
    assert job.description == "Build reliable data pipelines.\nPython"


def test_a_description_of_only_markup_is_rejected() -> None:
    with pytest.raises(RecordValidationError, match="description"):
        normalize(jobDescription="<div><span></span></div>")


def test_a_rejected_record_is_still_identifiable() -> None:
    with pytest.raises(RecordValidationError) as error:
        normalize(jobDescription="<br>")

    assert error.value.source_job_id == "153312"
    assert error.value.source_key == "jobicy"


@pytest.mark.parametrize(
    ("job_type", "expected"),
    [
        (["Full-Time"], EmploymentType.FULL_TIME),
        (["Part-Time"], EmploymentType.PART_TIME),
        (["Contract"], EmploymentType.CONTRACT),
        (["Freelance"], EmploymentType.CONTRACT),
        (["Internship"], EmploymentType.INTERNSHIP),
        (["Temporary"], EmploymentType.TEMPORARY),
        ("Full-Time", EmploymentType.FULL_TIME),
        (None, EmploymentType.UNSPECIFIED),
        ([], EmploymentType.UNSPECIFIED),
        (["Volunteer"], EmploymentType.UNSPECIFIED),
        (["Internship", "Part-Time"], EmploymentType.INTERNSHIP),
    ],
)
def test_employment_type_prefers_the_most_specific_signal(
    job_type: object,
    expected: EmploymentType,
) -> None:
    assert normalize(jobType=job_type).employment_type is expected


@pytest.mark.parametrize(
    ("geo", "expected"),
    [
        ("Canada,  Europe", "Canada, Europe"),
        ("LATAM,  Canada,  Europe", "LATAM, Canada, Europe"),
        ("Germany", "Germany"),
        ("", None),
        ("   ", None),
        ("Anywhere", None),
        ("  Anywhere  ", None),
        ("anywhere", None),
    ],
)
def test_location_collapses_double_spaces_and_drops_anywhere(
    geo: str,
    expected: str | None,
) -> None:
    """'Anywhere' is a workplace statement, not a place, so it is dropped."""
    assert to_location(geo) == expected


def test_a_normalized_record_carries_the_collapsed_location() -> None:
    assert normalize(jobGeo="Canada,  Europe").location == "Canada, Europe"


def test_a_normalized_record_drops_anywhere() -> None:
    assert normalize(jobGeo="Anywhere").location is None


def test_a_blank_geo_becomes_absent() -> None:
    assert normalize(jobGeo="   ").location is None


def test_a_missing_geo_stays_absent() -> None:
    record = raw_job()
    del record["jobGeo"]
    job = JobicyNormalizer().normalize(JobicyValidator().validate(record), record)

    assert job.location is None


def test_a_record_without_a_timestamp_has_no_publication_date() -> None:
    record = raw_job()
    del record["pubDate"]
    job = JobicyNormalizer().normalize(JobicyValidator().validate(record), record)

    assert job.published_at is None


def test_the_second_fixture_record_normalizes_too() -> None:
    raw = feed_jobs()[1]
    job = JobicyNormalizer().normalize(JobicyValidator().validate(raw), raw)

    assert job.title == "Senior DevOps Lead"
    assert job.workplace_type is WorkplaceType.REMOTE
    assert job.employment_type is EmploymentType.FULL_TIME
    assert job.location == "Germany"


def test_the_third_fixture_record_normalizes_too() -> None:
    raw = feed_jobs()[2]
    job = JobicyNormalizer().normalize(JobicyValidator().validate(raw), raw)

    assert job.title == "Chief Technology Officer"
    assert job.location == "LATAM, Canada, Europe"


def test_the_canonical_job_carries_no_provider_specific_fields() -> None:
    job = normalize()

    assert "jobType" not in job.model_dump()
    assert "jobGeo" not in job.model_dump()
    assert "jobSlug" not in job.model_dump()
