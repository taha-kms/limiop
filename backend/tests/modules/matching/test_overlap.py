from uuid import UUID

import pytest

from app.modules.matching.overlap import match_skills

PYTHON = UUID("11111111-1111-4111-8111-111111111111")
SQL = UUID("22222222-2222-4222-8222-222222222222")
DOCKER = UUID("33333333-3333-4333-8333-333333333333")


def test_a_candidate_with_everything_the_posting_asks_for_scores_one() -> None:
    result = match_skills({PYTHON, SQL}, {PYTHON, SQL})

    assert result.score == 1.0
    assert result.matched == tuple(sorted((PYTHON, SQL)))
    assert result.missing == ()


def test_a_partial_match_scores_the_share_it_covers() -> None:
    result = match_skills({PYTHON}, {PYTHON, SQL, DOCKER})

    assert result.score == pytest.approx(1 / 3)
    assert result.matched == (PYTHON,)
    assert result.missing == tuple(sorted((SQL, DOCKER)))


def test_a_candidate_sharing_nothing_scores_zero_and_is_told_what_is_missing() -> None:
    result = match_skills({DOCKER}, {PYTHON, SQL})

    assert result.score == 0.0
    assert result.matched == ()
    assert result.missing == tuple(sorted((PYTHON, SQL)))


def test_a_candidate_with_no_skills_matches_nothing() -> None:
    result = match_skills(set(), {PYTHON})

    assert result.score == 0.0
    assert result.missing == (PYTHON,)


def test_a_posting_naming_no_skills_scores_zero_rather_than_everything() -> None:
    """Two thirds of the catalogue has no extracted skills.

    Scoring silence as a perfect match would rank every one of those above
    every posting that matched genuinely, on the strength of asking nothing.
    """
    result = match_skills({PYTHON, SQL}, set())

    assert result.score == 0.0
    assert result.matched == ()
    assert result.missing == ()


def test_skills_the_posting_did_not_ask_for_are_not_held_against_the_candidate() -> None:
    """The asymmetry the formula exists to carry.

    A broader candidate is not a worse fit for a narrower job, which is exactly
    what dividing by the union would have said.
    """
    narrow = match_skills({PYTHON}, {PYTHON})
    broad = match_skills({PYTHON, SQL, DOCKER}, {PYTHON})

    assert narrow.score == broad.score == 1.0
    assert broad.matched == (PYTHON,)


def test_the_explanation_counts_what_the_posting_asked_for() -> None:
    result = match_skills({PYTHON}, {PYTHON, SQL})

    assert result.matched_count == 1
    assert result.required_count == 2


def test_a_score_is_always_between_zero_and_one() -> None:
    for candidate, required in (
        (set(), set()),
        ({PYTHON}, set()),
        (set(), {PYTHON}),
        ({PYTHON}, {PYTHON, SQL, DOCKER}),
        ({PYTHON, SQL, DOCKER}, {PYTHON}),
    ):
        assert 0.0 <= match_skills(candidate, required).score <= 1.0


def test_the_same_sets_always_produce_the_same_result() -> None:
    first = match_skills({DOCKER, PYTHON}, {SQL, PYTHON, DOCKER})
    second = match_skills({PYTHON, DOCKER}, {DOCKER, PYTHON, SQL})

    assert first == second
