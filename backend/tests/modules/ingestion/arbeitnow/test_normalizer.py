import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.modules.ingestion.arbeitnow.normalizer import (
    ArbeitnowNormalizer,
    to_employment_type,
    to_plain_text,
    to_workplace_type,
)
from app.modules.ingestion.arbeitnow.records import ArbeitnowValidator
from app.modules.ingestion.errors import RecordValidationError
from app.modules.jobs.domain import EmploymentType, WorkplaceType
from app.modules.jobs.schemas import NormalizedJob

FIXTURES = Path(__file__).parent / "fixtures"


def board_records() -> list[dict[str, Any]]:
    body = json.loads((FIXTURES / "job_board_page.json").read_text())
    records: list[dict[str, Any]] = body["data"]
    return records


def raw_record(**overrides: Any) -> dict[str, Any]:
    record = board_records()[0].copy()
    record.update(overrides)
    return record


def normalize(**overrides: Any) -> NormalizedJob:
    raw = raw_record(**overrides)
    return ArbeitnowNormalizer().normalize(ArbeitnowValidator().validate(raw), raw)


def test_a_representative_record_becomes_a_canonical_job() -> None:
    job = normalize()

    assert job.title == "Senior Data Engineer"
    assert job.company.display_name == "Acme GmbH"
    assert job.location == "Berlin"
    assert job.workplace_type is WorkplaceType.REMOTE
    assert job.employment_type is EmploymentType.FULL_TIME
    assert str(job.application_url).endswith("senior-data-engineer-berlin-123456")
    assert job.published_at == datetime(2025, 8, 18, 10, 40, tzinfo=UTC)
    assert job.expires_at is None


def test_normalization_is_deterministic() -> None:
    raw = raw_record()
    record = ArbeitnowValidator().validate(raw)
    normalizer = ArbeitnowNormalizer()

    first = normalizer.normalize(record, raw)
    second = normalizer.normalize(record, raw)

    assert first == second


def test_provenance_identifies_the_external_record() -> None:
    job = normalize()

    assert job.provenance.source_key == "arbeitnow"
    assert job.provenance.source_job_id == "senior-data-engineer-berlin-123456"
    assert str(job.provenance.source_url) == str(job.application_url)


def test_provenance_preserves_fields_that_validation_ignored() -> None:
    job = normalize()

    assert job.provenance.raw_payload is not None
    assert job.provenance.raw_payload["unexpected_new_field"] == {"added": "by the provider"}


def test_html_is_reduced_to_plain_text() -> None:
    job = normalize()

    assert "<" not in job.description
    assert job.description == "Build reliable data pipelines.\nPython"


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ("<p>One</p><p>Two</p>", "One\nTwo"),
        ("<ul><li>A</li><li>B</li></ul>", "A\nB"),
        ("Line one<br>Line two", "Line one\nLine two"),
        ("  spaced   out  ", "spaced out"),
        ("Caf&eacute; &amp; Bar", "Café & Bar"),
        ("<p>Unclosed paragraph", "Unclosed paragraph"),
        ("<div><span>Nested</span> text</div>", "Nested text"),
        ("plain text", "plain text"),
    ],
)
def test_markup_is_flattened_predictably(markup: str, expected: str) -> None:
    assert to_plain_text(markup) == expected


def test_script_and_style_bodies_never_reach_the_description() -> None:
    markup = "<p>Real text</p><script>alert('x')</script><style>.a{color:red}</style>"

    assert to_plain_text(markup) == "Real text"


def test_a_description_of_only_markup_is_rejected() -> None:
    with pytest.raises(RecordValidationError, match="description"):
        normalize(description="<div><span></span></div>")


def test_a_rejected_record_is_still_identifiable() -> None:
    with pytest.raises(RecordValidationError) as error:
        normalize(description="<br>")

    assert error.value.source_job_id == "senior-data-engineer-berlin-123456"
    assert error.value.source_key == "arbeitnow"


@pytest.mark.parametrize(
    ("job_types", "expected"),
    [
        (["full_time"], EmploymentType.FULL_TIME),
        (["part_time"], EmploymentType.PART_TIME),
        (["contract"], EmploymentType.CONTRACT),
        (["freelance"], EmploymentType.CONTRACT),
        (["internship"], EmploymentType.INTERNSHIP),
        (["temporary"], EmploymentType.TEMPORARY),
        (["Full-Time"], EmploymentType.FULL_TIME),
        (["  PART TIME  "], EmploymentType.PART_TIME),
        ([], EmploymentType.UNSPECIFIED),
        (["volunteer"], EmploymentType.UNSPECIFIED),
        (["internship", "part_time"], EmploymentType.INTERNSHIP),
        (["full_time", "contract"], EmploymentType.CONTRACT),
        (["temporary", "full_time"], EmploymentType.TEMPORARY),
    ],
)
def test_employment_type_prefers_the_most_specific_signal(
    job_types: list[str],
    expected: EmploymentType,
) -> None:
    assert to_employment_type(tuple(job_types)) is expected


def test_an_unmapped_job_type_does_not_lose_a_mapped_one() -> None:
    assert to_employment_type(("volunteer", "part_time")) is EmploymentType.PART_TIME


def test_a_remote_flag_becomes_remote() -> None:
    assert to_workplace_type(True) is WorkplaceType.REMOTE


def test_an_unflagged_job_is_unspecified_rather_than_onsite() -> None:
    assert to_workplace_type(False) is WorkplaceType.UNSPECIFIED


def test_a_blank_location_becomes_absent() -> None:
    assert normalize(location="   ").location is None


def test_a_missing_location_stays_absent() -> None:
    record = raw_record()
    del record["location"]
    job = ArbeitnowNormalizer().normalize(ArbeitnowValidator().validate(record), record)

    assert job.location is None


def test_a_record_without_a_timestamp_has_no_publication_date() -> None:
    record = raw_record()
    del record["created_at"]
    job = ArbeitnowNormalizer().normalize(ArbeitnowValidator().validate(record), record)

    assert job.published_at is None


def test_the_second_fixture_record_normalizes_too() -> None:
    raw = board_records()[1]
    job = ArbeitnowNormalizer().normalize(ArbeitnowValidator().validate(raw), raw)

    assert job.title == "Working Student Frontend"
    assert job.workplace_type is WorkplaceType.UNSPECIFIED
    assert job.employment_type is EmploymentType.INTERNSHIP
    assert job.location is None


def test_the_canonical_job_carries_no_provider_specific_fields() -> None:
    job = normalize()

    assert "tags" not in job.model_dump()
    assert "remote" not in job.model_dump()
    assert "slug" not in job.model_dump()
