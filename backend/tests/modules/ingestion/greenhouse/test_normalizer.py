import json
from pathlib import Path
from typing import Any

import pytest

from app.modules.ingestion.errors import RecordValidationError
from app.modules.ingestion.greenhouse.normalizer import GreenhouseNormalizer
from app.modules.ingestion.greenhouse.records import GreenhouseJobRecord, GreenhouseValidator
from app.modules.jobs.domain import EmploymentType, WorkplaceType
from app.modules.jobs.schemas import NormalizedJob

FIXTURE = Path(__file__).parent / "fixtures" / "board.json"


def fixture_records() -> list[dict[str, Any]]:
    body: dict[str, Any] = json.loads(FIXTURE.read_text())
    return [dict(job, board="hudl") for job in body["jobs"]]


def raw_record(**overrides: Any) -> dict[str, Any]:
    record = fixture_records()[0]
    record.update(overrides)
    return record


def validate(record: dict[str, Any]) -> GreenhouseJobRecord:
    """One call, so a raises block has a single thing that can throw."""
    return GreenhouseValidator().validate(record)


def normalize(**overrides: Any) -> NormalizedJob:
    raw = raw_record(**overrides)
    return GreenhouseNormalizer().normalize(GreenhouseValidator().validate(raw), raw)


def metadata(**fields: str) -> list[dict[str, Any]]:
    return [
        {"id": index, "name": name, "value": value}
        for index, (name, value) in enumerate(fields.items())
    ]


def test_a_real_posting_becomes_a_canonical_job() -> None:
    job = normalize()

    assert job.company.display_name == "Hudl"
    assert job.title
    assert job.description
    assert job.provenance.source_key == "greenhouse"


def test_normalization_is_deterministic() -> None:
    normalizer = GreenhouseNormalizer()
    raw = raw_record()
    record = GreenhouseValidator().validate(raw)

    first = normalizer.normalize(record, raw)
    second = normalizer.normalize(record, raw)

    assert first == second


def test_the_identifier_names_the_board_as_well_as_the_posting() -> None:
    """A posting identifier is only unique within the board that issued it."""
    job = normalize(id=99, board="anthropic")

    assert job.provenance.source_job_id == "anthropic:99"


def test_the_escaped_description_becomes_text() -> None:
    """Boards escape their own markup, the shape that once produced live tags."""
    job = normalize()

    assert "<" not in job.description
    assert "&lt;" not in job.description
    assert "&amp;" not in job.description


def test_an_escaped_script_cannot_reach_the_description() -> None:
    job = normalize(content="&lt;p&gt;Real text&lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;")

    assert job.description == "Real text"


@pytest.mark.parametrize(
    ("stated", "expected"),
    [
        pytest.param("On-Site", WorkplaceType.ONSITE, id="on site"),
        pytest.param("Remote", WorkplaceType.REMOTE, id="remote"),
        pytest.param("Hybrid", WorkplaceType.HYBRID, id="hybrid"),
        pytest.param("Hybrid (Travel-Required)", WorkplaceType.HYBRID, id="hybrid, qualified"),
        pytest.param("In Office", WorkplaceType.ONSITE, id="in office"),
    ],
)
def test_the_employer_states_the_arrangement(stated: str, expected: WorkplaceType) -> None:
    """Values are the employer's own words, not a vocabulary anyone controls."""
    assert normalize(metadata=metadata(**{"Location Type": stated})).workplace_type is expected


def test_this_is_the_first_source_that_can_say_onsite() -> None:
    job = normalize(metadata=metadata(**{"Location Type": "On-Site"}))

    assert job.workplace_type is WorkplaceType.ONSITE


def test_a_posting_stating_no_arrangement_stays_unspecified() -> None:
    job = normalize(metadata=[], location={"name": "Lincoln, NE, United States"})

    assert job.workplace_type is WorkplaceType.UNSPECIFIED


def test_an_arrangement_named_in_the_location_is_still_read() -> None:
    job = normalize(metadata=[], location={"name": "Remote - United States"})

    assert job.workplace_type is WorkplaceType.REMOTE


@pytest.mark.parametrize(
    ("stated", "expected"),
    [
        pytest.param("Full-Time", EmploymentType.FULL_TIME, id="full time"),
        pytest.param("Fixed Term", EmploymentType.TEMPORARY, id="fixed term"),
        pytest.param("Internship", EmploymentType.INTERNSHIP, id="internship"),
        pytest.param("Part Time", EmploymentType.PART_TIME, id="part time"),
    ],
)
def test_the_employer_states_the_relationship(stated: str, expected: EmploymentType) -> None:
    assert normalize(metadata=metadata(**{"Employment Type": stated})).employment_type is expected


def test_a_word_that_describes_something_else_maps_to_nothing() -> None:
    """`Regular` says the post is not fixed-term. It says nothing about hours."""
    job = normalize(metadata=metadata(**{"Employment Type": "Regular"}))

    assert job.employment_type is EmploymentType.UNSPECIFIED


def test_a_field_the_employer_invented_is_ignored() -> None:
    job = normalize(metadata=metadata(Chapter="Engineering"))

    assert job.employment_type is EmploymentType.UNSPECIFIED
    assert job.workplace_type is WorkplaceType.UNSPECIFIED


def test_publication_is_when_the_posting_appeared_not_when_it_changed() -> None:
    """An edit is not a repost, and the listing sorts on this."""
    job = normalize(
        first_published="2026-01-01T12:00:00+00:00",
        updated_at="2026-08-01T12:00:00+00:00",
    )

    assert job.published_at is not None
    assert job.published_at.year == 2026
    assert job.published_at.month == 1


def test_a_stated_deadline_becomes_the_expiry() -> None:
    job = normalize(
        first_published="2026-01-01T12:00:00+00:00",
        application_deadline="2026-03-01T12:00:00+00:00",
    )

    assert job.expires_at is not None


def test_no_deadline_is_the_ordinary_case() -> None:
    """Boards carry the field and leave it empty, so nothing may depend on it."""
    assert normalize().expires_at is None


def test_a_posting_with_no_location_has_none() -> None:
    assert normalize(location={"name": ""}).location is None


def test_the_raw_record_is_kept_for_reproducing_the_transformation() -> None:
    raw = raw_record()
    job = GreenhouseNormalizer().normalize(GreenhouseValidator().validate(raw), raw)

    assert job.provenance.raw_payload == raw


@pytest.mark.parametrize(
    "missing",
    ["title", "company_name", "content", "absolute_url", "id", "board"],
)
def test_a_record_missing_something_essential_is_rejected(missing: str) -> None:
    record = raw_record()
    del record[missing]

    with pytest.raises(RecordValidationError):
        validate(record)


def test_a_rejected_record_is_still_identifiable() -> None:
    record = raw_record()
    del record["title"]

    with pytest.raises(RecordValidationError) as raised:
        validate(record)

    assert raised.value.source_job_id == f"hudl:{record['id']}"


def test_a_rejection_never_repeats_provider_data() -> None:
    secret = "candidate-only-internal-note"
    record = raw_record(title=secret)
    del record["company_name"]

    with pytest.raises(RecordValidationError) as raised:
        validate(record)

    assert secret not in raised.value.message


def test_a_board_with_no_employer_fields_is_not_a_failure() -> None:
    """Some boards send null rather than an empty list."""
    assert normalize(metadata=None).employment_type is EmploymentType.UNSPECIFIED


def test_the_second_fixture_record_normalizes_too() -> None:
    raw = fixture_records()[1]
    job = GreenhouseNormalizer().normalize(GreenhouseValidator().validate(raw), raw)

    assert job.title
    assert "<" not in job.description


def test_a_record_the_canonical_contract_refuses_is_reported_not_raised_raw() -> None:
    """A board may send a title longer than the catalogue can store."""
    with pytest.raises(RecordValidationError) as raised:
        normalize(title="x" * 400)

    assert raised.value.source_job_id is not None
    assert raised.value.source_job_id.startswith("hudl:")
    assert "title" in raised.value.message
