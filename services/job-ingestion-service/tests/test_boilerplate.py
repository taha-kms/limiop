"""What an employer repeats about itself, and what it repeats about the role.

The second one is the whole difficulty. A block appearing in every posting is
not evidence that it says nothing about the job, so these tests are mostly
about what must survive.
"""

from typing import Any
from uuid import uuid4

import pytest

from job_ingestion.boilerplate import (
    BoilerplatePolicy,
    blocks,
    employer_marker,
    self_describing_blocks,
    strip_employer_boilerplate,
    without_blocks,
)
from job_ingestion.schemas import NormalizedJob

BLURB = "Acme is a public benefit corporation headquartered in San Francisco."
NOTICE = "Acme recruiters only contact you from @acme.com addresses."
REQUIREMENT = "Working fluency with data, including SQL."
ROLE = "You will build the pipelines that carry it."


def posting(*paragraphs: str, employer: str = "Acme GmbH") -> NormalizedJob:
    payload: dict[str, Any] = {
        "company": {"display_name": employer},
        "title": "Senior Data Engineer",
        "description": "\n".join(paragraphs),
        "application_url": f"https://acme.example.com/jobs/{uuid4().hex}",
        "provenance": {
            "source_key": "greenhouse",
            "source_job_id": uuid4().hex,
            "source_url": f"https://boards.example.com/{uuid4().hex}",
        },
    }
    return NormalizedJob.model_validate(payload)


def board(*paragraphs: str, count: int = 5, employer: str = "Acme GmbH") -> list[NormalizedJob]:
    """One employer's postings, each carrying the shared paragraphs and its own."""
    return [posting(*paragraphs, f"Posting {index}.", employer=employer) for index in range(count)]


def descriptions(jobs: list[NormalizedJob]) -> list[str]:
    return [job.description for job in jobs]


def test_a_block_the_employer_writes_about_itself_is_dropped() -> None:
    stripped, removal = strip_employer_boilerplate(board(BLURB, NOTICE, ROLE))

    assert all(BLURB not in job.description for job in stripped)
    assert all(NOTICE not in job.description for job in stripped)
    assert removal.postings == 5
    assert removal.blocks == 10
    assert removal.characters > 0


def test_a_repeated_requirement_is_kept() -> None:
    """The failure this rule exists to avoid.

    `Working fluency with data, including SQL` appears in every posting of the
    employer that prompted this. Repetition alone would take SQL out of the
    catalogue.
    """
    stripped, removal = strip_employer_boilerplate(board(REQUIREMENT, BLURB))

    assert all(REQUIREMENT in job.description for job in stripped)
    assert removal.blocks == 5


def test_an_employer_with_too_few_postings_keeps_everything() -> None:
    """Two postings sharing a paragraph is a coincidence, not a template."""
    stripped, removal = strip_employer_boilerplate(board(BLURB, count=4))

    assert all(BLURB in job.description for job in stripped)
    assert removal == removal.__class__()


def test_postings_the_catalogue_already_holds_establish_the_pattern() -> None:
    """A source that delivers an employer a few at a time is still an employer.

    Three postings are not a template. Three of a hundred are, and the three
    arriving now are the ones being written.
    """
    stripped, _ = strip_employer_boilerplate(
        board(BLURB, count=3),
        stored_postings={"acme gmbh": 100},
    )

    assert all(BLURB not in job.description for job in stripped)


def test_a_stored_count_below_the_minimum_still_changes_nothing() -> None:
    stripped, _ = strip_employer_boilerplate(
        board(BLURB, count=3),
        stored_postings={"acme gmbh": 4},
    )

    assert all(BLURB in job.description for job in stripped)


def test_the_share_is_measured_on_the_postings_in_hand() -> None:
    """Not on the catalogue's, whose copies may already have been stripped.

    Counting a stripped stored posting as one that lacks the block would make
    it evidence against the template it is proof of.
    """
    jobs = [*board(BLURB, count=2), *board(ROLE, count=2)]

    stripped, _ = strip_employer_boilerplate(jobs, stored_postings={"acme gmbh": 100})

    assert sum(BLURB in job.description for job in stripped) == 2


def test_another_employers_catalogue_is_not_this_ones() -> None:
    stripped, _ = strip_employer_boilerplate(
        board(BLURB, count=3),
        stored_postings={"globex ag": 100},
    )

    assert all(BLURB in job.description for job in stripped)


def test_a_block_in_only_some_postings_is_kept() -> None:
    jobs = [*board(ROLE, count=10), *board(BLURB, count=4)]

    stripped, _ = strip_employer_boilerplate(jobs)

    assert sum(BLURB in job.description for job in stripped) == 4


def test_one_employer_does_not_strip_another() -> None:
    """Blocks are counted per employer, or a shared aggregator template would go."""
    jobs = [*board(BLURB, count=5), *board(BLURB, count=5, employer="Globex AG")]

    stripped, _ = strip_employer_boilerplate(jobs)

    assert sum(BLURB in job.description for job in stripped) == 5


def test_a_name_is_matched_as_a_word_rather_than_as_a_substring() -> None:
    """An employer called `Init` must not own every sentence about initiative."""
    text = "We reward initiative and independence."
    stripped, _ = strip_employer_boilerplate(board(text, employer="Init"))

    assert all(text in job.description for job in stripped)


def test_the_same_block_punctuated_differently_is_still_the_same_block() -> None:
    postings = [
        posting(BLURB, ROLE),
        posting(BLURB.replace("San Francisco.", "San Francisco!"), ROLE),
        *board(BLURB, count=3),
    ]

    stripped, _ = strip_employer_boilerplate(postings)

    assert all("San Francisco" not in job.description for job in stripped)


def test_a_posting_made_only_of_boilerplate_keeps_its_text() -> None:
    """An empty description is not storable, and losing the posting is worse."""
    jobs = board(BLURB, count=5)
    jobs = [posting(BLURB), *jobs]

    stripped, _ = strip_employer_boilerplate(jobs)

    assert stripped[0].description == BLURB


def test_a_generic_second_word_in_a_name_owns_nothing() -> None:
    """`Quantum-Systems` must not take every repeated sentence about systems."""
    text = "Experience operating distributed systems in production."
    stripped, _ = strip_employer_boilerplate(board(text, employer="Quantum-Systems GmbH"))

    assert all(text in job.description for job in stripped)


def test_a_legal_form_is_not_the_employer_name() -> None:
    """Otherwise every German employer would own the same blocks."""
    assert employer_marker("Natuvion GmbH") == "natuvion"
    assert employer_marker("Tabel GmbH") == "tabel"


def test_a_name_of_only_short_words_falls_back_to_the_whole_thing() -> None:
    assert employer_marker("MY AG") == "my"


def test_nothing_is_dropped_from_an_employer_that_never_names_itself() -> None:
    assert self_describing_blocks("Acme GmbH", [ROLE] * 10, BoilerplatePolicy()) == frozenset()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("minimum_postings", 1, id="a pattern of one posting"),
        pytest.param("minimum_share", 0.0, id="a share of nothing"),
        pytest.param("minimum_share", 1.5, id="a share above everything"),
    ],
)
def test_a_policy_without_a_bound_is_refused(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        BoilerplatePolicy(**{field: value})  # type: ignore[arg-type]


def test_a_share_can_be_tightened_to_every_posting() -> None:
    strict = BoilerplatePolicy(minimum_share=1.0)
    jobs = [*board(BLURB, count=4), posting(ROLE)]

    assert self_describing_blocks("Acme GmbH", descriptions(jobs), strict) == frozenset()
    assert self_describing_blocks("Acme GmbH", descriptions(jobs), BoilerplatePolicy())


def test_blocks_are_the_paragraphs_the_normalizer_stored() -> None:
    assert blocks("One.\n\n  Two.  \n") == ["One.", "Two."]


def test_a_description_with_nothing_to_drop_comes_back_unchanged() -> None:
    assert without_blocks("One.\nTwo.", frozenset()) == "One.\nTwo."
