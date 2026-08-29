from uuid import UUID

import pytest

from app.modules.matching.tfidf import cosine, inverse_document_frequency

COMMON = UUID("cccccccc-0000-4000-8000-000000000001")
RARE = UUID("cccccccc-0000-4000-8000-000000000002")
OTHER = UUID("cccccccc-0000-4000-8000-000000000003")

CORPUS = [{COMMON, RARE}, {COMMON, OTHER}, {COMMON}]


def test_a_rare_concept_weighs_more_than_a_common_one() -> None:
    """The whole claim TF-IDF is being tested on."""
    weights = inverse_document_frequency(CORPUS)

    assert weights[RARE] > weights[COMMON]


def test_a_concept_in_every_document_still_weighs_something() -> None:
    """Smoothed, so a universal concept is discounted rather than erased."""
    weights = inverse_document_frequency([{COMMON}, {COMMON}])

    assert weights[COMMON] > 0


def test_an_empty_corpus_weighs_nothing_rather_than_dividing_by_zero() -> None:
    assert inverse_document_frequency([]) == {}


def test_sharing_nothing_scores_zero() -> None:
    weights = inverse_document_frequency(CORPUS)

    assert cosine({RARE}, {OTHER}, weights) == 0.0


def test_an_identical_skill_set_scores_one() -> None:
    weights = inverse_document_frequency(CORPUS)

    assert cosine({COMMON, RARE}, {COMMON, RARE}, weights) == pytest.approx(1.0)


def test_a_broader_candidate_scores_lower_for_the_same_posting() -> None:
    """The asymmetry the baseline refuses, reappearing as a lower number.

    Both candidates hold everything the posting asks for. Cosine normalises by
    the candidate's own vector, so the one who knows more is scored worse.
    """
    weights = inverse_document_frequency(CORPUS)

    exact = cosine({COMMON}, {COMMON}, weights)
    broad = cosine({COMMON, RARE, OTHER}, {COMMON}, weights)

    assert exact == pytest.approx(1.0)
    assert broad < exact


def test_an_empty_side_scores_zero() -> None:
    weights = inverse_document_frequency(CORPUS)

    assert cosine(set(), {COMMON}, weights) == 0.0
    assert cosine({COMMON}, set(), weights) == 0.0
