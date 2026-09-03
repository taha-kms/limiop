import json
from pathlib import Path
from typing import Any

import pytest

from job_ingestion.errors import RecordValidationError
from job_ingestion.pinpoint.records import PinpointValidator, readable_identifier

FIXTURE = Path(__file__).parent / "fixtures" / "postings.json"


def fixture_record(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(FIXTURE.read_text())
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
