import json
from pathlib import Path
from typing import Any

import pytest
from platform_db.models.catalog import EmploymentType, WorkplaceType

from job_ingestion.errors import RecordValidationError
from job_ingestion.polymer.normalizer import PolymerNormalizer
from job_ingestion.polymer.records import PolymerValidator
from job_ingestion.schemas import NormalizedJob

FIXTURE = Path(__file__).parent / "fixtures" / "detail.json"


def fixture_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = json.loads(FIXTURE.read_text())
    record["board"] = "aperturelabs"
    record.update(overrides)
    return record


def normalize(**overrides: Any) -> NormalizedJob:
    raw = fixture_record(**overrides)
    return PolymerNormalizer().normalize(PolymerValidator().validate(raw), raw)


def test_a_real_posting_becomes_a_canonical_job() -> None:
    job = normalize()

    assert job.company.display_name == "Aperture Labs"
    assert job.title
    assert "<" not in job.description
    assert job.location == "Phoenix, AZ"
    assert str(job.application_url).startswith("https://jobs.polymer.co/aperturelabs/30084")
    assert job.published_at is not None
    assert job.published_at.tzinfo is not None


def test_remote_friendly_reads_as_remote() -> None:
    """The vocabulary counts the word "remote"; that is its rule, not this normalizer's."""
    job = normalize()

    assert job.workplace_type is WorkplaceType.REMOTE


def test_full_time_reads_as_full_time() -> None:
    job = normalize()

    assert job.employment_type is EmploymentType.FULL_TIME


def test_the_identifier_names_the_board_as_well_as_the_posting() -> None:
    job = normalize()

    assert job.provenance.source_job_id == "aperturelabs:30084"


def test_a_record_the_canonical_contract_refuses_is_reported_not_raised_raw() -> None:
    """A board may send a title longer than the catalogue can store."""
    with pytest.raises(RecordValidationError) as raised:
        normalize(title="x" * 400)

    assert raised.value.source_job_id == "aperturelabs:30084"
    assert "title" in raised.value.message
