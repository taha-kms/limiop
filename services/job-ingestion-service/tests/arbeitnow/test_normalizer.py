import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from platform_db.models.catalog import EmploymentType, WorkplaceType

from job_ingestion.arbeitnow import normalizer
from job_ingestion.arbeitnow.normalizer import (
    ArbeitnowNormalizer,
    to_employment_type,
    to_plain_text,
    to_workplace_type,
)
from job_ingestion.arbeitnow.records import ArbeitnowValidator
from job_ingestion.errors import RecordValidationError
from job_ingestion.schemas import NormalizedJob

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
    assert to_workplace_type(True, None, ()) is WorkplaceType.REMOTE


def test_a_job_stating_nothing_anywhere_is_unspecified_rather_than_onsite() -> None:
    """Silence is not a claim, whatever the fields it arrives in."""
    assert to_workplace_type(False, "Berlin", ("python", "backend")) is WorkplaceType.UNSPECIFIED
    assert to_workplace_type(False, None, ()) is WorkplaceType.UNSPECIFIED


# The provider's `remote` flag is false on every one of these, which is why the
# other fields have to be read. Taken from the live catalog.
@pytest.mark.parametrize(
    ("location", "expected"),
    [
        pytest.param("Germany Remote", WorkplaceType.REMOTE, id="remote after a country"),
        pytest.param("Remote Deutschland", WorkplaceType.REMOTE, id="remote before a country"),
        pytest.param("Remote (Germany)", WorkplaceType.REMOTE, id="remote with a qualifier"),
        pytest.param("Remote (UTC+1 to UTC+2)", WorkplaceType.REMOTE, id="remote with an offset"),
        pytest.param("Berlin, Hybrid", WorkplaceType.HYBRID, id="hybrid after a comma"),
        pytest.param("Berlin Hybrid", WorkplaceType.HYBRID, id="hybrid after a city"),
        pytest.param("Homeoffice", WorkplaceType.REMOTE, id="german home office"),
        pytest.param("Home-Office, Köln", WorkplaceType.REMOTE, id="hyphenated home office"),
        pytest.param("München, vor Ort", WorkplaceType.ONSITE, id="german on site"),
        pytest.param("Teilweise Remote", WorkplaceType.HYBRID, id="partly remote is hybrid"),
    ],
)
def test_an_arrangement_stated_in_the_location_is_read(
    location: str,
    expected: WorkplaceType,
) -> None:
    assert to_workplace_type(False, location, ()) is expected


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        pytest.param("remote", WorkplaceType.REMOTE, id="remote tag"),
        pytest.param("homeoffice", WorkplaceType.REMOTE, id="home office tag"),
        pytest.param("hybrid", WorkplaceType.HYBRID, id="hybrid tag"),
    ],
)
def test_an_arrangement_stated_in_a_tag_is_read(tag: str, expected: WorkplaceType) -> None:
    assert to_workplace_type(False, "Berlin", ("python", tag)) is expected


@pytest.mark.parametrize(
    "location",
    [
        pytest.param("Remoteville", id="remote inside a place name"),
        pytest.param("Bremen", id="a city that merely contains the letters"),
        pytest.param("Hybridon", id="hybrid inside a longer word"),
        pytest.param("Onsted", id="onsite inside a longer word"),
    ],
)
def test_a_word_that_merely_contains_a_phrase_does_not_match(location: str) -> None:
    assert to_workplace_type(False, location, ()) is WorkplaceType.UNSPECIFIED


def test_the_most_specific_arrangement_wins_when_fields_disagree() -> None:
    """Hybrid asserts both arrangements, so it survives a contradicting remote."""
    assert to_workplace_type(True, "Berlin, Hybrid", ()) is WorkplaceType.HYBRID
    assert to_workplace_type(False, "Remote", ("hybrid",)) is WorkplaceType.HYBRID


def test_onsite_never_outranks_a_stated_remote_arrangement() -> None:
    assert to_workplace_type(False, "Berlin, vor Ort", ("remote",)) is WorkplaceType.REMOTE


def test_a_normalized_record_carries_the_arrangement_from_its_location() -> None:
    assert normalize(remote=False, location="Berlin, Hybrid").workplace_type is (
        WorkplaceType.HYBRID
    )


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


# The provider escapes its own markup on a minority of postings, so a single
# flattening pass decodes the entities and hands back the tags it should have
# removed. These cover the shape seen in the live catalog.

ESCAPED_POSTING = (
    "&lt;p&gt;&lt;strong&gt;Working Student - Product Engineer&lt;/strong&gt;&lt;/p&gt;\n"
    "&lt;p&gt;Over 4 million merchants use our card readers.&lt;/p&gt;"
)


def test_escaped_markup_becomes_text_rather_than_tags() -> None:
    flattened = to_plain_text(ESCAPED_POSTING)

    assert (
        flattened
        == "Working Student - Product Engineer\nOver 4 million merchants use our card readers."
    )
    assert "<" not in flattened


@pytest.mark.parametrize(
    "markup",
    [
        pytest.param("&lt;script&gt;alert(1)&lt;/script&gt;", id="escaped script"),
        pytest.param("&amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt;", id="twice escaped"),
    ],
)
def test_an_escaped_script_body_cannot_reach_a_description(markup: str) -> None:
    assert to_plain_text(markup) == ""


@pytest.mark.parametrize(
    "markup",
    [
        pytest.param("&lt;img src=x onerror=alert(1)&gt;", id="escaped event handler"),
        pytest.param('&lt;div class="intro"&gt;Hello&lt;/div&gt;', id="escaped element"),
        pytest.param('&lt;a href="javascript:alert(1)"&gt;click&lt;/a&gt;', id="escaped link"),
    ],
)
def test_no_escaped_element_survives_as_markup(markup: str) -> None:
    flattened = to_plain_text(markup)

    assert "<" not in flattened
    assert ">" not in flattened


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("Plain description with no markup at all.", id="plain prose"),
        pytest.param("Salary: 50k & up", id="bare ampersand"),
        pytest.param("Requires a < b reasoning", id="bare less-than"),
        pytest.param("Line one\nLine two", id="paragraph break"),
    ],
)
def test_text_that_is_already_plain_is_returned_unchanged(text: str) -> None:
    assert to_plain_text(text) == text


def test_flattening_settles_rather_than_repeating() -> None:
    """Each changing pass shortens the text, so the result is its own fixed point."""
    once = to_plain_text(ESCAPED_POSTING)

    assert to_plain_text(once) == once


def test_flattening_terminates_on_deeply_escaped_markup() -> None:
    markup = "<p>text</p>"
    for _ in range(4):
        markup = markup.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    assert to_plain_text(markup) == "text"


def test_flattening_gives_up_rather_than_looping(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bound is unreachable while passes shorten the text, so force it.

    What it guarantees is termination, not a clean result: a pass budget spent
    without settling returns what it had rather than running on.
    """
    monkeypatch.setattr(normalizer, "MAX_FLATTENING_PASSES", 1)

    assert to_plain_text("&lt;p&gt;text&lt;/p&gt;") == "<p>text</p>"
