from datetime import UTC, datetime

import pytest

from job_ingestion.adzuna.records import AdzunaJobRecord, AdzunaValidator, provenance_id
from job_ingestion.errors import RecordValidationError
from tests.adzuna.support import page_records, posting, without


def test_a_representative_record_validates() -> None:
    record = AdzunaValidator().validate(posting())

    assert record.id == "5312407781"
    assert record.country == "gb"
    assert record.title == "Senior Data Engineer"
    assert record.description.startswith("We are looking for a Senior Data Engineer")
    assert record.company.display_name == "Northwind Analytics"
    assert record.location.display_name == "London, UK"
    assert record.location.area == ("UK", "London")
    assert str(record.redirect_url).startswith("https://www.adzuna.co.uk/jobs/land/ad/5312407781")
    assert record.contract_type == "permanent"
    assert record.contract_time == "full_time"
    assert record.created == datetime(2026, 9, 14, 8, 15, 22, tzinfo=UTC)


@pytest.mark.parametrize("country", ["gb", "de"])
def test_every_record_in_a_fixture_page_validates(country: str) -> None:
    validator = AdzunaValidator()

    records = [validator.validate(record) for record in page_records(country)]

    assert len(records) == 3
    assert {record.country for record in records} == {country}


def test_unexpected_provider_fields_are_ignored() -> None:
    record = AdzunaValidator().validate(posting(brand_new_field="surprise"))

    assert not hasattr(record, "brand_new_field")
    assert not hasattr(record, "adref")
    assert not hasattr(record.company, "__CLASS__")


@pytest.mark.parametrize("company", [{"display_name": ""}, {"display_name": "   "}, {}, None])
def test_a_record_without_an_employer_is_refused(company: object) -> None:
    """The catalogue files every posting under an employer, so a record that
    names none cannot be stored, however complete the rest of it is."""
    with pytest.raises(RecordValidationError, match="company"):
        AdzunaValidator().validate(posting(company=company))


def test_a_missing_company_is_refused() -> None:
    with pytest.raises(RecordValidationError, match="company"):
        AdzunaValidator().validate(without("company"))


def test_a_missing_location_leaves_the_place_unstated() -> None:
    record = AdzunaValidator().validate(without("location"))

    assert record.location.display_name == ""
    assert record.location.area == ()


def test_missing_contract_fields_fall_back_to_empty() -> None:
    record = AdzunaValidator().validate(without("contract_type", "contract_time"))

    assert record.contract_type == ""
    assert record.contract_time == ""


def test_a_missing_created_date_is_allowed() -> None:
    record = AdzunaValidator().validate(without("created"))

    assert record.created is None


def test_surrounding_whitespace_is_trimmed() -> None:
    record = AdzunaValidator().validate(
        posting(title="  Senior Data Engineer  ", company={"display_name": " Northwind "})
    )

    assert record.title == "Senior Data Engineer"
    assert record.company.display_name == "Northwind"


def test_a_validated_record_is_immutable() -> None:
    record = AdzunaValidator().validate(posting())

    with pytest.raises(ValueError, match="frozen"):
        record.title = "Something else"


@pytest.mark.parametrize("field", ["id", "country", "title", "description", "redirect_url"])
def test_a_missing_required_field_is_reported_by_name(field: str) -> None:
    with pytest.raises(RecordValidationError, match=f"{field}: Field required"):
        AdzunaValidator().validate(without(field))


@pytest.mark.parametrize("field", ["id", "country", "title", "description"])
def test_a_blank_required_field_is_rejected(field: str) -> None:
    with pytest.raises(RecordValidationError, match=field):
        AdzunaValidator().validate(posting(**{field: "   "}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", ["5312407781"]),
        ("redirect_url", "not-a-url"),
        ("created", "2026-09-14T08:15:22"),
        ("created", "whenever"),
        ("location", {"display_name": "London", "area": "London"}),
        ("contract_time", ["full_time"]),
    ],
)
def test_a_malformed_field_is_reported_by_name(field: str, value: object) -> None:
    with pytest.raises(RecordValidationError, match=field):
        AdzunaValidator().validate(posting(**{field: value}))


def test_several_problems_are_reported_together() -> None:
    with pytest.raises(RecordValidationError) as error:
        AdzunaValidator().validate(posting(title="", redirect_url="not-a-url"))

    assert "title" in error.value.message
    assert "redirect_url" in error.value.message


def test_a_failure_names_the_record_by_country_and_id() -> None:
    with pytest.raises(RecordValidationError) as error:
        AdzunaValidator().validate(posting(title=""))

    assert error.value.source_job_id == "gb:5312407781"
    assert error.value.source_key == "adzuna"


def test_a_failure_before_stamping_names_the_bare_id() -> None:
    with pytest.raises(RecordValidationError) as error:
        AdzunaValidator().validate(without("country"))

    assert error.value.source_job_id == "5312407781"


def test_a_numeric_id_is_read_as_the_string_it_is_documented_to_be() -> None:
    record = AdzunaValidator().validate(posting(id=5312407781))

    assert record.id == "5312407781"


def test_a_failure_still_names_a_record_whose_id_is_numeric() -> None:
    with pytest.raises(RecordValidationError) as error:
        AdzunaValidator().validate(posting(id=5312407781, title=""))

    assert error.value.source_job_id == "gb:5312407781"


@pytest.mark.parametrize("identifier", [None, "", "   ", True, ["42"]])
def test_a_failure_tolerates_an_unusable_id(identifier: object) -> None:
    with pytest.raises(RecordValidationError) as error:
        AdzunaValidator().validate(posting(id=identifier, title=""))

    assert error.value.source_job_id is None


def test_a_failure_never_repeats_provider_data() -> None:
    secret = "candidate-only-internal-note"

    with pytest.raises(RecordValidationError) as error:
        AdzunaValidator().validate(posting(title="", description=secret))

    assert secret not in error.value.message


def test_provenance_id_joins_country_and_id() -> None:
    assert provenance_id("de", "5311980427") == "de:5311980427"


def test_the_provider_record_is_not_the_canonical_contract() -> None:
    assert "workplace_type" not in AdzunaJobRecord.model_fields
    assert "employment_type" not in AdzunaJobRecord.model_fields
    assert "application_url" not in AdzunaJobRecord.model_fields
