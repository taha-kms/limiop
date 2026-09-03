import json
from pathlib import Path
from typing import Any

import pytest

from job_ingestion.errors import RecordValidationError
from job_ingestion.polymer.records import PolymerValidator, readable_identifier

FIXTURE = Path(__file__).parent / "fixtures" / "detail.json"


def fixture_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = json.loads(FIXTURE.read_text())
    record["board"] = "aperturelabs"
    record.update(overrides)
    return record


def test_the_detail_fixture_merged_with_a_board_validates() -> None:
    record = PolymerValidator().validate(fixture_record())

    assert record.board == "aperturelabs"
    assert record.id == 30084
    assert record.organization_name == "Aperture Labs"
    assert record.description


def test_a_record_missing_its_description_is_refused() -> None:
    record = fixture_record()
    del record["description"]

    with pytest.raises(RecordValidationError) as raised:
        PolymerValidator().validate(record)

    assert "description" in raised.value.message


def test_the_identifier_names_the_board_as_well_as_the_posting() -> None:
    assert readable_identifier(fixture_record()) == "aperturelabs:30084"


def test_an_unidentifiable_record_has_no_readable_identifier() -> None:
    record = fixture_record()
    del record["board"]

    assert readable_identifier(record) is None
