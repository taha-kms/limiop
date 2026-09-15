import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from platform_db.models.catalog import EmploymentType, WorkplaceType

from job_ingestion.errors import RecordValidationError
from job_ingestion.remotive.normalizer import RemotiveNormalizer
from job_ingestion.remotive.records import RemotiveValidator
from job_ingestion.schemas import NormalizedJob

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_jobs() -> list[dict[str, Any]]:
    body: dict[str, Any] = json.loads((FIXTURES / "remote_jobs.json").read_text())
    jobs: list[dict[str, Any]] = body["jobs"]
    return jobs


def raw_record(**overrides: Any) -> dict[str, Any]:
    record = fixture_jobs()[0].copy()
    record.update(overrides)
    return record


def normalize(**overrides: Any) -> NormalizedJob:
    raw = raw_record(**overrides)
    return RemotiveNormalizer().normalize(RemotiveValidator().validate(raw), raw)


def test_a_representative_record_becomes_a_canonical_job() -> None:
    job = normalize()

    assert job.title == "Remote Office Assistant"
    assert job.company.display_name == "Coalition Technologies"
    assert job.location == "Worldwide"
    assert job.workplace_type is WorkplaceType.REMOTE
    assert job.employment_type is EmploymentType.FULL_TIME
    assert str(job.application_url).endswith("remote-office-assistant-1680495")
    assert job.published_at == datetime(2026, 9, 11, 20, 16, 48, tzinfo=UTC)
    assert job.expires_at is None


def test_normalization_is_deterministic() -> None:
    raw = raw_record()
    record = RemotiveValidator().validate(raw)
    normalizer = RemotiveNormalizer()

    first = normalizer.normalize(record, raw)
    second = normalizer.normalize(record, raw)

    assert first == second


def test_provenance_identifies_the_external_record() -> None:
    job = normalize()

    assert job.provenance.source_key == "remotive"
    assert job.provenance.source_job_id == "1680495"
    assert str(job.provenance.source_url) == str(job.application_url)


def test_provenance_preserves_the_raw_integer_id() -> None:
    """The provenance identifier is stringified for storage, but the raw
    payload keeps the JSON number the provider actually sent."""
    job = normalize()

    assert job.provenance.raw_payload is not None
    assert job.provenance.raw_payload["id"] == 1680495


def test_html_is_reduced_to_plain_text() -> None:
    job = normalize()

    assert "<" not in job.description
    assert "Coalition Technologies is seeking" in job.description


def test_a_tracking_pixel_leaves_no_trace_in_the_description() -> None:
    """Every fixture posting ends with an `<img>` tracking pixel; it carries no
    text, so flattening removes it without a Remotive-specific footer rule."""
    job = normalize()

    assert "blank.gif" not in job.description
    assert "img" not in job.description.lower()


@pytest.mark.parametrize(
    ("job_type", "expected"),
    [
        ("full_time", EmploymentType.FULL_TIME),
        ("part_time", EmploymentType.PART_TIME),
        ("contract", EmploymentType.CONTRACT),
        ("freelance", EmploymentType.CONTRACT),
        ("internship", EmploymentType.INTERNSHIP),
        ("other", EmploymentType.UNSPECIFIED),
        ("", EmploymentType.UNSPECIFIED),
    ],
)
def test_employment_type_is_read_from_the_job_type_field(
    job_type: str,
    expected: EmploymentType,
) -> None:
    job = normalize(job_type=job_type)

    assert job.employment_type is expected


def test_an_underscored_job_type_is_read_as_two_words() -> None:
    """`full_time` is a token, not a phrase: the shared vocabulary only
    matches `full time`, and `to_token` is what folds the underscore into a
    space before the phrase lookup runs."""
    job = normalize(job_type="full_time")

    assert job.employment_type is EmploymentType.FULL_TIME


def test_every_posting_is_remote_regardless_of_stated_fields() -> None:
    """Remotive lists only remote roles: the arrangement is asserted by the
    feed itself, not read out of any one field the way an aggregator that
    mixes arrangements requires."""
    job = normalize(candidate_required_location="Onsite in Berlin, no remote work")

    assert job.workplace_type is WorkplaceType.REMOTE


def test_the_stated_location_is_kept_as_is() -> None:
    """`Worldwide` is what the employer said, not a placeholder to discard."""
    job = normalize(candidate_required_location="Worldwide")

    assert job.location == "Worldwide"


def test_a_multi_country_location_is_kept_as_is() -> None:
    raw = fixture_jobs()[1]
    job = RemotiveNormalizer().normalize(RemotiveValidator().validate(raw), raw)

    assert job.location == "France, Japan, Turkey, Vietnam, Mexico, Norway"


def test_a_blank_location_becomes_absent() -> None:
    job = normalize(candidate_required_location="")

    assert job.location is None


def test_a_missing_location_stays_absent() -> None:
    record = raw_record()
    del record["candidate_required_location"]
    job = RemotiveNormalizer().normalize(RemotiveValidator().validate(record), record)

    assert job.location is None


def test_a_record_without_a_timestamp_has_no_publication_date() -> None:
    record = raw_record()
    del record["publication_date"]
    job = RemotiveNormalizer().normalize(RemotiveValidator().validate(record), record)

    assert job.published_at is None


def test_the_second_fixture_record_normalizes_too() -> None:
    raw = fixture_jobs()[1]
    job = RemotiveNormalizer().normalize(RemotiveValidator().validate(raw), raw)

    assert job.title == "AI Response Evaluator"
    assert job.employment_type is EmploymentType.CONTRACT
    assert job.workplace_type is WorkplaceType.REMOTE
    assert job.provenance.source_job_id == "2091126"


def test_the_third_fixture_record_normalizes_too() -> None:
    raw = fixture_jobs()[2]
    job = RemotiveNormalizer().normalize(RemotiveValidator().validate(raw), raw)

    assert job.title == "Inside Sales Contractor"
    assert job.employment_type is EmploymentType.FULL_TIME
    assert job.provenance.source_job_id == "2086540"


def test_the_canonical_job_carries_no_provider_specific_fields() -> None:
    job = normalize()

    assert "tags" not in job.model_dump()
    assert "category" not in job.model_dump()
    assert "salary" not in job.model_dump()
    assert "company_logo" not in job.model_dump()


def test_a_description_of_only_markup_is_rejected() -> None:
    with pytest.raises(RecordValidationError, match="description"):
        normalize(description="<div><span></span></div>")


def test_a_rejected_record_is_still_identifiable() -> None:
    with pytest.raises(RecordValidationError) as error:
        normalize(description="<br>")

    assert error.value.source_job_id == "1680495"
    assert error.value.source_key == "remotive"
