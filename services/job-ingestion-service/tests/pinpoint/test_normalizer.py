import json
from pathlib import Path
from typing import Any

import pytest
from platform_db.models.catalog import EmploymentType, WorkplaceType

from job_ingestion.errors import RecordValidationError
from job_ingestion.pinpoint.normalizer import PinpointNormalizer
from job_ingestion.pinpoint.records import PinpointValidator
from job_ingestion.schemas import NormalizedJob

FIXTURE = Path(__file__).parent / "fixtures" / "postings.json"


def fixture_record(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(FIXTURE.read_text())
    record: dict[str, Any] = dict(body["data"][0])
    record["board"] = "workwithus"
    record.update(overrides)
    return record


def normalize(**overrides: Any) -> NormalizedJob:
    raw = fixture_record(**overrides)
    return PinpointNormalizer().normalize(PinpointValidator().validate(raw), raw)


def test_a_real_posting_becomes_a_canonical_job() -> None:
    job = normalize()

    assert job.title
    assert job.location == "Remote"
    assert str(job.application_url) == (
        "https://workwithus.pinpointhq.com/en/postings/ce6c9e5c-a2d3-42b0-a01e-9edeae315b04"
    )
    assert job.published_at is None
    assert job.expires_at is None


def test_the_company_is_the_configured_board_slug() -> None:
    """The feed never names an employer; the board slug is all a run has."""
    job = normalize()

    assert job.company.display_name == "workwithus"


def test_the_description_joins_the_postings_own_text_and_leaves_out_benefits() -> None:
    job = normalize()

    assert "Ellis" in job.description  # from `description`
    assert "Sales legal" in job.description  # from `key_responsibilities`
    assert "qualified lawyer" in job.description  # from `skills_knowledge_expertise`
    assert "Comprehensive healthcare" not in job.description  # `benefits`, left out
    assert "<" not in job.description


def test_fully_remote_reads_as_remote() -> None:
    job = normalize()

    assert job.workplace_type is WorkplaceType.REMOTE


def test_full_time_reads_as_full_time() -> None:
    job = normalize()

    assert job.employment_type is EmploymentType.FULL_TIME


def test_a_deadline_becomes_an_aware_expiry() -> None:
    job = normalize(deadline_at="2027-01-15T00:00:00Z")

    assert job.expires_at is not None
    assert job.expires_at.tzinfo is not None


def test_the_identifier_names_the_board_as_well_as_the_posting() -> None:
    job = normalize()

    assert job.provenance.source_job_id == "workwithus:559663"


def test_a_record_the_canonical_contract_refuses_is_reported_not_raised_raw() -> None:
    """A board may send a title longer than the catalogue can store."""
    with pytest.raises(RecordValidationError) as raised:
        normalize(title="x" * 400)

    assert raised.value.source_job_id == "workwithus:559663"
    assert "title" in raised.value.message
