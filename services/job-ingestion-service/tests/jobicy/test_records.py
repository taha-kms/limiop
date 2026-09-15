import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from job_ingestion.errors import RecordValidationError
from job_ingestion.jobicy.records import JobicyJobRecord, JobicyValidator

FIXTURES = Path(__file__).parent / "fixtures"


def feed_jobs() -> list[dict[str, Any]]:
    body = json.loads((FIXTURES / "remote_jobs.json").read_text())
    jobs: list[dict[str, Any]] = body["jobs"]
    return jobs


def valid_record(**overrides: Any) -> dict[str, Any]:
    record = feed_jobs()[0].copy()
    record.update(overrides)
    return record


def without(*fields: str) -> dict[str, Any]:
    record = valid_record()
    for field in fields:
        del record[field]
    return record


def test_a_representative_record_validates() -> None:
    record = JobicyValidator().validate(valid_record())

    assert record.id == "153312"
    assert record.jobTitle == "SVP, Product"
    assert record.companyName == "Toptal"
    assert record.jobDescription.startswith("<h3>About Toptal</h3>")
    assert str(record.url) == "https://jobicy.com/jobs/153312-svp-product"
    assert record.jobGeo == "Canada,  Europe"
    assert record.jobType == ("Full-Time",)
    assert record.jobLevel == "Director"
    assert record.pubDate == datetime(2026, 9, 15, 6, 3, 2, tzinfo=UTC)


def test_every_record_in_the_fixture_page_validates() -> None:
    validator = JobicyValidator()

    records = [validator.validate(job) for job in feed_jobs()]

    assert [record.id for record in records] == ["153312", "153313", "153308"]


def test_unexpected_provider_fields_are_ignored() -> None:
    record = JobicyValidator().validate(valid_record(brand_new_field="surprise"))

    assert not hasattr(record, "brand_new_field")
    assert record.id == "153312"


def test_a_numeric_id_is_coerced_to_a_string() -> None:
    """The feed sends `id` as a JSON number; every downstream use is textual."""
    record = JobicyValidator().validate(valid_record(id=99))

    assert record.id == "99"


def test_a_string_id_is_left_alone() -> None:
    record = JobicyValidator().validate(valid_record(id="already-a-string"))

    assert record.id == "already-a-string"


def test_optional_provider_fields_fall_back_to_empty_values() -> None:
    record = JobicyValidator().validate(without("jobGeo", "jobType", "jobLevel", "pubDate"))

    assert record.jobGeo == ""
    assert record.jobType == ()
    assert record.jobLevel == ""
    assert record.pubDate is None


def test_job_type_accepts_a_plain_string() -> None:
    record = JobicyValidator().validate(valid_record(jobType="Part-Time"))

    assert record.jobType == ("Part-Time",)


def test_job_type_accepts_null() -> None:
    record = JobicyValidator().validate(valid_record(jobType=None))

    assert record.jobType == ()


def test_job_type_accepts_a_list() -> None:
    record = JobicyValidator().validate(valid_record(jobType=["Full-Time", "Contract"]))

    assert record.jobType == ("Full-Time", "Contract")


def test_a_missing_timestamp_is_allowed() -> None:
    record = JobicyValidator().validate(without("pubDate"))

    assert record.pubDate is None


def test_surrounding_whitespace_is_trimmed() -> None:
    record = JobicyValidator().validate(valid_record(jobTitle="  SVP, Product  "))

    assert record.jobTitle == "SVP, Product"


def test_a_validated_record_is_immutable() -> None:
    record = JobicyValidator().validate(valid_record())

    with pytest.raises(ValueError, match="frozen"):
        record.jobTitle = "Something else"


@pytest.mark.parametrize("field", ["id", "jobTitle", "companyName", "jobDescription", "url"])
def test_a_missing_required_field_is_reported_by_name(field: str) -> None:
    with pytest.raises(RecordValidationError, match=field):
        JobicyValidator().validate(without(field))


@pytest.mark.parametrize("field", ["jobTitle", "companyName", "jobDescription"])
def test_a_blank_required_field_is_rejected(field: str) -> None:
    with pytest.raises(RecordValidationError, match=field):
        JobicyValidator().validate(valid_record(**{field: "   "}))


@pytest.mark.parametrize("field", ["id", "jobTitle", "companyName", "jobDescription", "url"])
def test_a_null_required_field_is_rejected(field: str) -> None:
    with pytest.raises(RecordValidationError, match=field):
        JobicyValidator().validate(valid_record(**{field: None}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "not-a-url"),
        ("url", 42),
        ("jobType", {"name": "full-time"}),
        ("jobType", [{"name": "full-time"}]),
        ("pubDate", "whenever"),
        ("jobTitle", ["SVP, Product"]),
    ],
)
def test_a_malformed_field_is_reported_by_name(field: str, value: object) -> None:
    with pytest.raises(RecordValidationError, match=field):
        JobicyValidator().validate(valid_record(**{field: value}))


def test_a_failure_names_the_record_when_the_id_is_readable() -> None:
    with pytest.raises(RecordValidationError) as error:
        JobicyValidator().validate(valid_record(jobTitle=""))

    assert error.value.source_job_id == "153312"
    assert error.value.source_key == "jobicy"


def test_a_failure_names_the_record_when_the_id_is_already_a_string() -> None:
    with pytest.raises(RecordValidationError) as error:
        JobicyValidator().validate(valid_record(id="already-a-string", jobTitle=""))

    assert error.value.source_job_id == "already-a-string"


def test_a_failure_names_the_record_when_the_id_is_numeric() -> None:
    with pytest.raises(RecordValidationError) as error:
        JobicyValidator().validate(valid_record(id=99, jobTitle=""))

    assert error.value.source_job_id == "99"


@pytest.mark.parametrize("identifier", [None, "", "   ", [1], {}])
def test_a_failure_tolerates_an_unusable_id(identifier: object) -> None:
    with pytest.raises(RecordValidationError) as error:
        JobicyValidator().validate(valid_record(id=identifier, jobTitle=""))

    assert error.value.source_job_id is None


def test_a_failure_never_repeats_provider_data() -> None:
    secret = "candidate-only-internal-note"

    with pytest.raises(RecordValidationError) as error:
        JobicyValidator().validate(valid_record(jobTitle="", jobDescription=secret))

    assert secret not in error.value.message


def test_a_record_missing_everything_is_rejected() -> None:
    with pytest.raises(RecordValidationError) as error:
        JobicyValidator().validate({})

    assert error.value.source_job_id is None
    for field in ("id", "jobTitle", "companyName", "jobDescription", "url"):
        assert field in error.value.message


def test_the_provider_record_is_not_the_canonical_contract() -> None:
    assert "workplace_type" not in JobicyJobRecord.model_fields
    assert "employment_type" not in JobicyJobRecord.model_fields
    assert "application_url" not in JobicyJobRecord.model_fields
