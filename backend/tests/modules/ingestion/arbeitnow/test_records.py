import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.modules.ingestion.arbeitnow.records import ArbeitnowJobRecord, ArbeitnowValidator
from app.modules.ingestion.errors import RecordValidationError

FIXTURES = Path(__file__).parent / "fixtures"


def board_records() -> list[dict[str, Any]]:
    body = json.loads((FIXTURES / "job_board_page.json").read_text())
    records: list[dict[str, Any]] = body["data"]
    return records


def valid_record(**overrides: Any) -> dict[str, Any]:
    record = board_records()[0].copy()
    record.update(overrides)
    return record


def without(*fields: str) -> dict[str, Any]:
    record = valid_record()
    for field in fields:
        del record[field]
    return record


def test_a_representative_record_validates() -> None:
    record = ArbeitnowValidator().validate(valid_record())

    assert record.slug == "senior-data-engineer-berlin-123456"
    assert record.title == "Senior Data Engineer"
    assert record.company_name == "Acme GmbH"
    assert record.description.startswith("<p>Build reliable data pipelines.")
    assert str(record.url).endswith("senior-data-engineer-berlin-123456")
    assert record.remote is True
    assert record.location == "Berlin"
    assert record.tags == ("python", "sql")
    assert record.job_types == ("full_time",)
    assert record.created_at == datetime(2025, 8, 18, 10, 40, tzinfo=UTC)


def test_every_record_in_the_fixture_page_validates() -> None:
    validator = ArbeitnowValidator()

    records = [validator.validate(record) for record in board_records()]

    assert [record.slug for record in records] == [
        "senior-data-engineer-berlin-123456",
        "working-student-frontend-654321",
    ]


def test_unexpected_provider_fields_are_ignored() -> None:
    record = ArbeitnowValidator().validate(valid_record(brand_new_field="surprise"))

    assert not hasattr(record, "brand_new_field")
    assert record.slug == "senior-data-engineer-berlin-123456"


def test_an_epoch_timestamp_becomes_a_timezone_aware_value() -> None:
    record = ArbeitnowValidator().validate(valid_record(created_at=1755427200))

    assert record.created_at == datetime(2025, 8, 17, 10, 40, tzinfo=UTC)


def test_a_missing_timestamp_is_allowed() -> None:
    record = ArbeitnowValidator().validate(without("created_at"))

    assert record.created_at is None


def test_optional_provider_fields_fall_back_to_empty_values() -> None:
    record = ArbeitnowValidator().validate(without("remote", "tags", "job_types", "location"))

    assert record.remote is False
    assert record.tags == ()
    assert record.job_types == ()
    assert record.location is None


def test_an_empty_location_is_preserved_for_the_normalizer_to_interpret() -> None:
    record = ArbeitnowValidator().validate(valid_record(location="   "))

    assert record.location == ""


def test_surrounding_whitespace_is_trimmed() -> None:
    record = ArbeitnowValidator().validate(valid_record(title="  Senior Data Engineer  "))

    assert record.title == "Senior Data Engineer"


def test_a_validated_record_is_immutable() -> None:
    record = ArbeitnowValidator().validate(valid_record())

    with pytest.raises(ValueError, match="frozen"):
        record.title = "Something else"


@pytest.mark.parametrize("field", ["slug", "title", "company_name", "description", "url"])
def test_a_missing_required_field_is_reported_by_name(field: str) -> None:
    with pytest.raises(RecordValidationError, match=f"{field}: Field required"):
        ArbeitnowValidator().validate(without(field))


@pytest.mark.parametrize("field", ["slug", "title", "company_name", "description"])
def test_a_blank_required_field_is_rejected(field: str) -> None:
    with pytest.raises(RecordValidationError, match=field):
        ArbeitnowValidator().validate(valid_record(**{field: "   "}))


@pytest.mark.parametrize("field", ["slug", "title", "company_name", "description", "url"])
def test_a_null_required_field_is_rejected(field: str) -> None:
    with pytest.raises(RecordValidationError, match=field):
        ArbeitnowValidator().validate(valid_record(**{field: None}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "not-a-url"),
        ("url", 42),
        ("remote", "yes please"),
        ("tags", "python"),
        ("tags", [{"name": "python"}]),
        ("job_types", 7),
        ("created_at", "whenever"),
        ("title", ["Senior Data Engineer"]),
    ],
)
def test_a_malformed_field_is_reported_by_name(field: str, value: object) -> None:
    with pytest.raises(RecordValidationError, match=field):
        ArbeitnowValidator().validate(valid_record(**{field: value}))


def test_several_problems_are_reported_together() -> None:
    broken = valid_record(title="", url="not-a-url")
    del broken["company_name"]

    with pytest.raises(RecordValidationError) as error:
        ArbeitnowValidator().validate(broken)

    assert "title" in error.value.message
    assert "company_name" in error.value.message
    assert "url" in error.value.message


def test_a_failure_names_the_record_when_the_slug_is_readable() -> None:
    with pytest.raises(RecordValidationError) as error:
        ArbeitnowValidator().validate(valid_record(title=""))

    assert error.value.source_job_id == "senior-data-engineer-berlin-123456"
    assert error.value.source_key == "arbeitnow"


@pytest.mark.parametrize("slug", [None, "", "   ", 42, ["a"]])
def test_a_failure_tolerates_an_unusable_slug(slug: object) -> None:
    with pytest.raises(RecordValidationError) as error:
        ArbeitnowValidator().validate(valid_record(slug=slug, title=""))

    assert error.value.source_job_id is None


def test_a_failure_never_repeats_provider_data() -> None:
    secret = "candidate-only-internal-note"

    with pytest.raises(RecordValidationError) as error:
        ArbeitnowValidator().validate(valid_record(title="", description=secret))

    assert secret not in error.value.message


def test_a_record_missing_everything_is_rejected() -> None:
    with pytest.raises(RecordValidationError) as error:
        ArbeitnowValidator().validate({})

    assert error.value.source_job_id is None
    for field in ("slug", "title", "company_name", "description", "url"):
        assert field in error.value.message


def test_the_provider_record_is_not_the_canonical_contract() -> None:
    assert "workplace_type" not in ArbeitnowJobRecord.model_fields
    assert "employment_type" not in ArbeitnowJobRecord.model_fields
    assert "application_url" not in ArbeitnowJobRecord.model_fields
