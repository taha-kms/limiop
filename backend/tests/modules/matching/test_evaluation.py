"""The committed baseline, pinned.

These numbers are the gate later matchers are compared against, so a change to
the matcher that moves them should fail here rather than quietly rewriting what
everything else is measured by.
"""

from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from app.modules.matching.evaluation import (
    OVERLAP,
    TFIDF,
    evaluate,
    load_corpus,
    ndcg,
    rank,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CORPUS_PATH = REPOSITORY_ROOT / "docs/matching-evaluation/corpus.json"
RESULTS = REPOSITORY_ROOT / "docs/matching-evaluation/results.md"
CORPUS = load_corpus(CORPUS_PATH)


@pytest.fixture(scope="module")
def measured() -> dict[str, object]:
    return evaluate(CORPUS)


def corpus_jobs() -> dict[str, set[UUID]]:
    return {
        cast(str, job["key"]): {UUID(value) for value in cast(list[str], job["skills"])}
        for job in cast(list[dict[str, object]], CORPUS["jobs"])
    }


def test_the_committed_baseline_is_reproducible(measured: dict[str, object]) -> None:
    assert measured["ndcg@5"] == 0.8055
    assert measured["precision@1"] == 0.8333
    assert measured["candidates"] == 6
    assert measured["jobs"] == 12


def test_the_documented_numbers_match_the_measured_ones(measured: dict[str, object]) -> None:
    """So the write-up cannot drift from what the command prints."""
    document = RESULTS.read_text(encoding="utf-8")

    assert f"| NDCG@5 | **{measured['ndcg@5']}** |" in document
    assert f"| Precision@1 | **{measured['precision@1']}** |" in document


def test_every_offered_result_names_something_the_candidate_has(
    measured: dict[str, object],
) -> None:
    """A result offered with nothing matched is a number pretending to be advice."""
    assert measured["share_naming_a_matched_skill"] == 1.0


def test_the_corpus_grades_by_hand_rather_than_by_the_matcher() -> None:
    """Every graded posting exists, and no candidate grades all of them.

    A corpus that calls every posting relevant cannot tell a ranking from a
    shuffle.
    """
    jobs = corpus_jobs()
    for entry in cast(list[dict[str, object]], CORPUS["candidates"]):
        relevance = cast(dict[str, int], entry["relevance"])
        assert set(relevance) <= set(jobs)
        assert len(relevance) < len(jobs)


def test_a_candidate_with_one_generic_skill_ranks_at_zero(
    measured: dict[str, object],
) -> None:
    """The finding, pinned.

    `newcomer` holds one concept and gets a confident-looking ranking worth
    nothing. The endpoint refuses to rank a profile this thin; if that ever
    stops being true, this fails.
    """
    rows = {
        cast(str, row["candidate"]): row
        for row in cast(list[dict[str, object]], measured["per_candidate"])
    }

    assert rows["newcomer"]["ndcg@5"] == 0.0
    assert rows["newcomer"]["precision@1"] == 0


def test_ranking_is_stable_when_scores_tie() -> None:
    """Ties break on the job key, so paging cannot repeat or skip a posting."""
    jobs = corpus_jobs()

    forwards = [entry.job for entry in rank(set(), jobs, {})]
    backwards = [entry.job for entry in rank(set(), dict(reversed(jobs.items())), {})]

    assert forwards == backwards == sorted(jobs)


def test_a_better_order_scores_higher_than_a_worse_one() -> None:
    """The metric has to tell them apart, or it measures nothing."""
    candidates = cast(list[dict[str, object]], CORPUS["candidates"])
    practitioner = {UUID(value) for value in cast(list[str], candidates[1]["skills"])}
    ordered = rank(practitioner, corpus_jobs(), {"ml-engineer": 2, "backend-engineer": 1})

    assert ndcg(ordered, 5) > ndcg(list(reversed(ordered)), 5)


def test_nothing_relevant_scores_zero_rather_than_dividing_by_zero() -> None:
    assert ndcg([], 5) == 0.0


def test_tfidf_is_measured_on_the_same_corpus_and_metrics() -> None:
    """Comparing two measurements instead of two matchers proves nothing."""
    overlap = evaluate(CORPUS, matcher=OVERLAP)
    tfidf = evaluate(CORPUS, matcher=TFIDF)

    assert overlap["candidates"] == tfidf["candidates"]
    assert overlap["jobs"] == tfidf["jobs"]
    assert overlap["corpus_version"] == tfidf["corpus_version"]


def test_the_committed_tfidf_comparison_is_reproducible() -> None:
    tfidf = evaluate(CORPUS, matcher=TFIDF)

    assert tfidf["ndcg@5"] == 0.8156
    assert tfidf["precision@1"] == 0.8333


def test_the_documented_comparison_matches_the_measured_one() -> None:
    overlap = evaluate(CORPUS, matcher=OVERLAP)
    tfidf = evaluate(CORPUS, matcher=TFIDF)
    document = (REPOSITORY_ROOT / "docs/matching-evaluation/tfidf.md").read_text(encoding="utf-8")

    assert f"| NDCG@5 | {overlap['ndcg@5']} | **{tfidf['ndcg@5']}** |" in document


def test_tfidf_scores_a_complete_match_below_one() -> None:
    """The finding that decided it.

    A candidate holding every skill a posting asks for is shown "3 of 3 skills"
    and a score of 0.84. Nothing in the explanation produces that number.
    """
    tfidf = evaluate(CORPUS, matcher=TFIDF)
    seller = next(
        row
        for row in cast(list[dict[str, object]], tfidf["per_candidate"])
        if row["candidate"] == "seller"
    )
    best = cast(list[dict[str, object]], seller["top"])[0]

    assert best["job"] == "account-executive"
    assert best["matched"] == best["required"]
    assert cast(float, best["score"]) < 1.0
