from enum import StrEnum

import pytest

from app.modules.jobs.domain import (
    EXCERPT_LENGTH,
    EmploymentType,
    JobStatus,
    WorkplaceType,
    to_excerpt,
)


@pytest.mark.parametrize(
    ("enum_type", "expected"),
    [
        (
            WorkplaceType,
            {
                "REMOTE": "remote",
                "HYBRID": "hybrid",
                "ONSITE": "onsite",
                "UNSPECIFIED": "unspecified",
            },
        ),
        (
            EmploymentType,
            {
                "FULL_TIME": "full-time",
                "PART_TIME": "part-time",
                "CONTRACT": "contract",
                "INTERNSHIP": "internship",
                "TEMPORARY": "temporary",
                "UNSPECIFIED": "unspecified",
            },
        ),
        (
            JobStatus,
            {
                "ACTIVE": "active",
                "EXPIRED": "expired",
                "REMOVED": "removed",
            },
        ),
    ],
)
def test_canonical_job_vocabulary(
    enum_type: type[StrEnum],
    expected: dict[str, str],
) -> None:
    assert {member.name: member.value for member in enum_type} == expected
    assert all(str(member) == member.value for member in enum_type)


@pytest.mark.parametrize("enum_type", [WorkplaceType, EmploymentType, JobStatus])
def test_canonical_job_vocabulary_rejects_unsupported_input(
    enum_type: type[StrEnum],
) -> None:
    with pytest.raises(ValueError):
        enum_type("unsupported")


def test_unspecified_classifications_are_explicit() -> None:
    assert WorkplaceType.UNSPECIFIED.value == "unspecified"
    assert EmploymentType.UNSPECIFIED.value == "unspecified"


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        pytest.param("Short enough.", "Short enough.", id="shorter than the limit"),
        pytest.param(
            "Opening thought.\nSecond paragraph.",
            "Opening thought. Second paragraph.",
            id="joins paragraphs",
        ),
        pytest.param("  Padded.  \n  More.  ", "Padded. More.", id="trimmed"),
        pytest.param("One.\n\n\nTwo.", "One. Two.", id="blank lines collapse"),
        pytest.param("", "", id="empty"),
    ],
)
def test_an_excerpt_keeps_what_fits(description: str, expected: str) -> None:
    assert to_excerpt(description) == expected


def test_an_excerpt_reaches_past_an_opening_heading() -> None:
    """Real postings open with a heading, so the first paragraph is a label."""
    excerpt = to_excerpt("Why Mozilla?\nWe build the open web for everyone.")

    assert excerpt == "Why Mozilla? We build the open web for everyone."


def test_a_long_excerpt_is_cut_at_a_word_boundary() -> None:
    excerpt = to_excerpt("alpha " * 200)

    assert excerpt.endswith("…")
    assert len(excerpt) <= EXCERPT_LENGTH + 1
    assert "alph…" not in excerpt
    assert excerpt.removesuffix("…").strip().split()[-1] == "alpha"


def test_an_unbroken_run_still_produces_a_bounded_excerpt() -> None:
    """No space to cut at, so the word boundary rule cannot help here."""
    excerpt = to_excerpt("x" * 400)

    assert excerpt == "x" * EXCERPT_LENGTH + "…"


def test_an_excerpt_respects_a_caller_supplied_limit() -> None:
    assert to_excerpt("one two three four", limit=7) == "one two…"
