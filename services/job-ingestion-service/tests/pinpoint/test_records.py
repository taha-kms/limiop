import json
from pathlib import Path
from typing import Any

import pytest

from job_ingestion.errors import RecordValidationError
from job_ingestion.pinpoint.records import PinpointValidator, readable_identifier

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "postings.json"
REMOTE_FIXTURE = FIXTURES / "remote_posting.json"


def fixture_record(fixture: Path = FIXTURE, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(fixture.read_text())
    record: dict[str, Any] = dict(body["data"][0])
    record["board"] = "workwithus"
    record.update(overrides)
    return record


def test_the_fixture_posting_merged_with_a_board_validates() -> None:
    record = PinpointValidator().validate(fixture_record())

    assert record.board == "workwithus"
    assert record.id == "559663"
    assert record.title
    assert record.description


def test_a_posting_with_a_null_location_validates_with_an_empty_location() -> None:
    record = PinpointValidator().validate(fixture_record(location=None))

    assert record.location.name == ""
    assert record.location.city == ""


def test_a_posting_that_sends_null_for_its_optional_strings_validates() -> None:
    """Remote and multi-location postings carry null, not an empty string."""
    record = PinpointValidator().validate(fixture_record(REMOTE_FIXTURE))

    assert record.id == "601204"
    assert record.location.city == ""
    assert record.location.name == "Multiple locations"
    assert record.workplace_type == ""
    assert record.workplace_type_text == ""
    assert record.employment_type == ""
    assert record.employment_type_text == ""
    assert record.key_responsibilities == ""
    assert record.skills_knowledge_expertise == ""


def test_a_required_field_sent_as_null_is_still_refused() -> None:
    with pytest.raises(RecordValidationError) as raised:
        PinpointValidator().validate(fixture_record(REMOTE_FIXTURE, title=None))

    assert raised.value.source_job_id == "workwithus:601204"
    assert "title" in raised.value.message


def test_a_record_missing_its_description_is_refused() -> None:
    record = fixture_record()
    del record["description"]

    with pytest.raises(RecordValidationError) as raised:
        PinpointValidator().validate(record)

    assert "description" in raised.value.message


def test_the_identifier_names_the_board_as_well_as_the_posting() -> None:
    assert readable_identifier(fixture_record()) == "workwithus:559663"


def test_an_unidentifiable_record_has_no_readable_identifier() -> None:
    record = fixture_record()
    del record["board"]

    assert readable_identifier(record) is None
