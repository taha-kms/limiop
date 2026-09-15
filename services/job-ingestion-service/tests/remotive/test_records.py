from datetime import UTC, datetime
from typing import Any

import pytest

from job_ingestion.errors import RecordValidationError
from job_ingestion.remotive.records import RemotiveJobRecord, RemotiveValidator


def valid_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": 1680495,
        "url": "https://remotive.com/remote-jobs/marketing/remote-office-assistant-1680495",
        "title": "Remote Office Assistant",
        "company_name": "Coalition Technologies ",
        "company_logo": "https://remotive.com/job/1680495/logo",
        "category": "Marketing",
        "tags": ["css", "html"],
        "job_type": "full_time",
        "publication_date": "2026-09-11T20:16:48",
        "candidate_required_location": "Worldwide",
        "salary": "$31,2k- $52k",
        "description": "<p>Support administrative tasks.</p>",
        "company_logo_url": "https://remotive.com/job/1680495/logo",
    }
    record.update(overrides)
    return record


def without(*fields: str) -> dict[str, Any]:
    record = valid_record()
    for field in fields:
        del record[field]
    return record


def test_a_representative_record_validates() -> None:
    record = RemotiveValidator().validate(valid_record())

    assert record.id == 1680495
    assert record.title == "Remote Office Assistant"
    assert record.company_name == "Coalition Technologies"
    assert record.description.startswith("<p>Support administrative")
    assert str(record.url).endswith("remote-office-assistant-1680495")
    assert record.job_type == "full_time"
    assert record.candidate_required_location == "Worldwide"
    assert record.publication_date == datetime(2026, 9, 11, 20, 16, 48, tzinfo=UTC)


def test_ids_in_the_feed_are_json_numbers_not_strings() -> None:
    """Remotive's `id` is a bare JSON number in every posting the live feed
    returns, not the quoted string the API documentation's prose implies."""
    record = RemotiveValidator().validate(valid_record(id=2091126))

    assert record.id == 2091126
    assert isinstance(record.id, int)


def test_trailing_whitespace_in_company_name_is_stripped() -> None:
    record = RemotiveValidator().validate(valid_record(company_name="Coalition Technologies "))

    assert record.company_name == "Coalition Technologies"


def test_a_naive_publication_date_becomes_aware_utc() -> None:
    """Remotive's feed carries no offset -- `2026-09-11T20:16:48` rather than
    `...+00:00` -- and its API documentation states the feed publishes in UTC.
    A naive value here is that omission, not a provider mistake, so it is
    stamped UTC rather than refused."""
    record = RemotiveValidator().validate(valid_record(publication_date="2026-09-11T20:16:48"))

    assert record.publication_date == datetime(2026, 9, 11, 20, 16, 48, tzinfo=UTC)
    assert record.publication_date is not None
    assert record.publication_date.tzinfo is UTC


def test_an_already_aware_publication_date_is_left_alone() -> None:
    record = RemotiveValidator().validate(
        valid_record(publication_date="2026-09-11T20:16:48+02:00")
    )

    assert record.publication_date == datetime(2026, 9, 11, 18, 16, 48, tzinfo=UTC)


def test_a_missing_publication_date_is_allowed() -> None:
    record = RemotiveValidator().validate(without("publication_date"))

    assert record.publication_date is None


def test_optional_provider_fields_fall_back_to_empty_values() -> None:
    record = RemotiveValidator().validate(without("job_type", "candidate_required_location"))

    assert record.job_type == ""
    assert record.candidate_required_location == ""


def test_unexpected_provider_fields_are_ignored() -> None:
    record = RemotiveValidator().validate(valid_record(company_logo="surprise"))

    assert not hasattr(record, "company_logo")
    assert record.id == 1680495


def test_a_validated_record_is_immutable() -> None:
    record = RemotiveValidator().validate(valid_record())

    with pytest.raises(ValueError, match="frozen"):
        record.title = "Something else"


@pytest.mark.parametrize("field", ["id", "title", "company_name", "description", "url"])
def test_a_missing_required_field_is_reported_by_name(field: str) -> None:
    with pytest.raises(RecordValidationError, match=f"{field}: Field required"):
        RemotiveValidator().validate(without(field))


@pytest.mark.parametrize("field", ["title", "company_name", "description"])
def test_a_blank_required_field_is_rejected(field: str) -> None:
    with pytest.raises(RecordValidationError, match=field):
        RemotiveValidator().validate(valid_record(**{field: "   "}))


def test_a_missing_description_is_refused() -> None:
    with pytest.raises(RecordValidationError, match="description"):
        RemotiveValidator().validate(without("description"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "not-a-url"),
        ("url", 42),
        ("id", "not-a-number"),
        ("id", None),
        ("title", ["Remote Office Assistant"]),
        ("publication_date", "whenever"),
    ],
)
def test_a_malformed_field_is_reported_by_name(field: str, value: object) -> None:
    with pytest.raises(RecordValidationError, match=field):
        RemotiveValidator().validate(valid_record(**{field: value}))


def test_several_problems_are_reported_together() -> None:
    broken = valid_record(title="", url="not-a-url")
    del broken["company_name"]

    with pytest.raises(RecordValidationError) as error:
        RemotiveValidator().validate(broken)

    assert "title" in error.value.message
    assert "company_name" in error.value.message
    assert "url" in error.value.message


def test_a_failure_names_the_record_when_the_id_is_readable() -> None:
    with pytest.raises(RecordValidationError) as error:
        RemotiveValidator().validate(valid_record(title=""))

    assert error.value.source_job_id == "1680495"
    assert error.value.source_key == "remotive"


@pytest.mark.parametrize("identifier", [None, "", "   ", ["a"], 1680495.5])
def test_a_failure_tolerates_an_unusable_id(identifier: object) -> None:
    with pytest.raises(RecordValidationError) as error:
        RemotiveValidator().validate(valid_record(id=identifier, title=""))

    assert error.value.source_job_id is None


def test_a_failure_never_repeats_provider_data() -> None:
    secret = "candidate-only-internal-note"

    with pytest.raises(RecordValidationError) as error:
        RemotiveValidator().validate(valid_record(title="", description=secret))

    assert secret not in error.value.message


def test_a_record_missing_everything_is_rejected() -> None:
    with pytest.raises(RecordValidationError) as error:
        RemotiveValidator().validate({})

    assert error.value.source_job_id is None
    for field in ("id", "title", "company_name", "description", "url"):
        assert field in error.value.message


def test_the_provider_record_is_not_the_canonical_contract() -> None:
    assert "workplace_type" not in RemotiveJobRecord.model_fields
    assert "employment_type" not in RemotiveJobRecord.model_fields
    assert "application_url" not in RemotiveJobRecord.model_fields
