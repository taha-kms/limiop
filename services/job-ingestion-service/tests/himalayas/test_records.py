import json
from pathlib import Path
from typing import Any

import pytest

from job_ingestion.errors import RecordValidationError
from job_ingestion.himalayas.records import HimalayasJobRecord, HimalayasValidator

FIXTURES = Path(__file__).parent / "fixtures"


def page_records(name: str = "page_one.json") -> list[dict[str, Any]]:
    body = json.loads((FIXTURES / name).read_text())
    records: list[dict[str, Any]] = body["jobs"]
    return records


def valid_record(**overrides: Any) -> dict[str, Any]:
    record = page_records()[0].copy()
    record.update(overrides)
    return record


def without(*fields: str) -> dict[str, Any]:
    record = valid_record()
    for field in fields:
        del record[field]
    return record


def test_a_representative_record_validates() -> None:
    record = HimalayasValidator().validate(valid_record())

    assert record.title == "Director, Value Attainment & Analysis"
    assert record.companyName == "abridge"
    assert record.description.startswith("<h3><strong>About Abridge</strong></h3>")
    assert str(record.guid).endswith("director-value-attainment-analysis")
    assert str(record.applicationLink).endswith("director-value-attainment-analysis")
    assert record.employmentType == "Full Time"
    assert record.locationRestrictions == ("United States",)
    assert record.pubDate == 1789465009
    assert record.expiryDate == 1794649007


def test_every_record_in_the_fixture_page_validates() -> None:
    validator = HimalayasValidator()

    records = [validator.validate(record) for record in page_records()]

    assert [record.title for record in records] == [
        "Director, Value Attainment & Analysis",
        "Senior Software Engineer, Partnerships & Integrations (Open-Source)",
    ]


def test_unexpected_provider_fields_are_ignored() -> None:
    record = HimalayasValidator().validate(valid_record(brand_new_field="surprise"))

    assert not hasattr(record, "brand_new_field")
    assert record.title == "Director, Value Attainment & Analysis"


def test_a_numeric_pub_date_string_is_accepted() -> None:
    record = HimalayasValidator().validate(valid_record(pubDate="1789465009"))

    assert record.pubDate == 1789465009


def test_a_numeric_expiry_date_string_is_accepted() -> None:
    record = HimalayasValidator().validate(valid_record(expiryDate="1794649007"))

    assert record.expiryDate == 1794649007


def test_a_missing_pub_date_is_allowed() -> None:
    record = HimalayasValidator().validate(without("pubDate"))

    assert record.pubDate is None


def test_a_missing_expiry_date_is_allowed() -> None:
    record = HimalayasValidator().validate(without("expiryDate"))

    assert record.expiryDate is None


def test_a_negative_pub_date_is_rejected() -> None:
    with pytest.raises(RecordValidationError, match="pubDate"):
        HimalayasValidator().validate(valid_record(pubDate=-1))


def test_a_negative_expiry_date_is_rejected() -> None:
    with pytest.raises(RecordValidationError, match="expiryDate"):
        HimalayasValidator().validate(valid_record(expiryDate=-1))


def test_null_location_restrictions_becomes_an_empty_tuple() -> None:
    record = HimalayasValidator().validate(valid_record(locationRestrictions=None))

    assert record.locationRestrictions == ()


def test_a_missing_location_restrictions_becomes_an_empty_tuple() -> None:
    record = HimalayasValidator().validate(without("locationRestrictions"))

    assert record.locationRestrictions == ()


def test_a_single_location_restriction_string_becomes_a_one_element_tuple() -> None:
    record = HimalayasValidator().validate(valid_record(locationRestrictions="Remote"))

    assert record.locationRestrictions == ("Remote",)


def test_a_missing_employment_type_falls_back_to_empty() -> None:
    record = HimalayasValidator().validate(without("employmentType"))

    assert record.employmentType == ""


def test_surrounding_whitespace_is_trimmed() -> None:
    record = HimalayasValidator().validate(valid_record(title="  Director  "))

    assert record.title == "Director"


def test_a_validated_record_is_immutable() -> None:
    record = HimalayasValidator().validate(valid_record())

    with pytest.raises(ValueError, match="frozen"):
        record.title = "Something else"


@pytest.mark.parametrize(
    "field", ["title", "companyName", "description", "guid", "applicationLink"]
)
def test_a_missing_required_field_is_reported_by_name(field: str) -> None:
    with pytest.raises(RecordValidationError, match=f"{field}: Field required"):
        HimalayasValidator().validate(without(field))


@pytest.mark.parametrize("field", ["title", "companyName", "description"])
def test_a_blank_required_field_is_rejected(field: str) -> None:
    with pytest.raises(RecordValidationError, match=field):
        HimalayasValidator().validate(valid_record(**{field: "   "}))


@pytest.mark.parametrize(
    "field", ["title", "companyName", "description", "guid", "applicationLink"]
)
def test_a_null_required_field_is_rejected(field: str) -> None:
    with pytest.raises(RecordValidationError, match=field):
        HimalayasValidator().validate(valid_record(**{field: None}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("guid", "not-a-url"),
        ("guid", 42),
        ("applicationLink", "not-a-url"),
        ("employmentType", ["Full Time"]),
        ("pubDate", "whenever"),
        ("expiryDate", "whenever"),
        ("locationRestrictions", 7),
    ],
)
def test_a_malformed_field_is_reported_by_name(field: str, value: object) -> None:
    with pytest.raises(RecordValidationError, match=field):
        HimalayasValidator().validate(valid_record(**{field: value}))


def test_several_problems_are_reported_together() -> None:
    broken = valid_record(title="", guid="not-a-url")
    del broken["companyName"]

    with pytest.raises(RecordValidationError) as error:
        HimalayasValidator().validate(broken)

    assert "title" in error.value.message
    assert "companyName" in error.value.message
    assert "guid" in error.value.message


def test_a_failure_names_the_record_when_the_guid_is_readable() -> None:
    with pytest.raises(RecordValidationError) as error:
        HimalayasValidator().validate(valid_record(title=""))

    assert error.value.source_job_id == (
        "https://himalayas.app/companies/abridge/jobs/director-value-attainment-analysis"
    )
    assert error.value.source_key == "himalayas"


@pytest.mark.parametrize("guid", [None, "", "   ", 42, ["a"]])
def test_a_failure_tolerates_an_unusable_guid(guid: object) -> None:
    with pytest.raises(RecordValidationError) as error:
        HimalayasValidator().validate(valid_record(guid=guid, title=""))

    assert error.value.source_job_id is None


def test_a_failure_still_names_the_record_when_the_guid_is_malformed() -> None:
    """A malformed URL is still a printable identifier for reporting, exactly
    like a well-formed one: only blankness makes an identifier unusable."""
    with pytest.raises(RecordValidationError) as error:
        HimalayasValidator().validate(valid_record(guid="not-a-url", title=""))

    assert error.value.source_job_id == "not-a-url"


def test_a_failure_never_repeats_provider_data() -> None:
    secret = "candidate-only-internal-note"

    with pytest.raises(RecordValidationError) as error:
        HimalayasValidator().validate(valid_record(title="", description=secret))

    assert secret not in error.value.message


def test_a_record_missing_everything_is_rejected() -> None:
    with pytest.raises(RecordValidationError) as error:
        HimalayasValidator().validate({})

    assert error.value.source_job_id is None
    for field in ("title", "companyName", "description", "guid", "applicationLink"):
        assert field in error.value.message


def test_the_provider_record_is_not_the_canonical_contract() -> None:
    assert "workplace_type" not in HimalayasJobRecord.model_fields
    assert "employment_type" not in HimalayasJobRecord.model_fields
    assert "application_url" not in HimalayasJobRecord.model_fields
