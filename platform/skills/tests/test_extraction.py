from uuid import UUID

import pytest

from platform_skills import Mention, extract_mentions

POSTGRESQL_ID = UUID("25a5528c-45a4-4a1d-a43c-45f3f4e79a20")
DATA_ANALYSIS_ID = UUID("a31f19fc-9e50-41d6-8b4e-ae59e438b40f")


def test_extracts_exact_surface_normalized_form_and_span() -> None:
    text = "We use POSTGRES and data-analysis daily."

    mentions = extract_mentions(
        text,
        {
            "Postgres": POSTGRESQL_ID,
            "data analysis": DATA_ANALYSIS_ID,
        },
    )

    assert mentions == (
        Mention("POSTGRES", "postgres", 7, 15, POSTGRESQL_ID),
        Mention("data-analysis", "data analysis", 20, 33, DATA_ANALYSIS_ID),
    )
    assert mentions[0].span == (7, 15)
    assert mentions[0].resolved is True


def test_longest_phrase_wins_and_results_follow_source_order() -> None:
    text = "Python supports data analysis and analysis workflows."

    mentions = extract_mentions(
        text,
        {
            "analysis": None,
            "data analysis": DATA_ANALYSIS_ID,
            "python": POSTGRESQL_ID,
        },
    )

    assert [mention.surface_form for mention in mentions] == [
        "Python",
        "data analysis",
        "analysis",
    ]
    assert mentions[1].concept_id == DATA_ANALYSIS_ID
    assert mentions[2].resolved is False
    assert mentions[2].concept_id is None


def test_short_forms_match_whole_tokens_not_substrings() -> None:
    mentions = extract_mentions("Said AI enables painting.", {"ai": None})

    assert mentions == (Mention("AI", "ai", 5, 7, None),)


def test_repeated_non_overlapping_mentions_are_preserved() -> None:
    mentions = extract_mentions("SQL, sql, and SQL.", {"sql": POSTGRESQL_ID})

    assert [mention.surface_form for mention in mentions] == ["SQL", "sql", "SQL"]
    assert [mention.span for mention in mentions] == [(0, 3), (5, 8), (14, 17)]


def test_unicode_case_folding_and_separator_variants_match() -> None:
    mentions = extract_mentions(
        "STRASSE and cross_functional",
        {"Straße": None, "cross-functional": DATA_ANALYSIS_ID},
    )

    assert [mention.normalized_form for mention in mentions] == [
        "strasse",
        "cross functional",
    ]


def test_empty_text_or_vocabulary_has_no_mentions() -> None:
    assert extract_mentions("", {"sql": POSTGRESQL_ID}) == ()
    assert extract_mentions("SQL", {}) == ()


def test_blank_vocabulary_form_is_rejected() -> None:
    with pytest.raises(ValueError, match="surface forms must contain a term"):
        extract_mentions("anything", {"  --  ": None})


def test_conflicting_forms_after_normalization_are_rejected() -> None:
    with pytest.raises(ValueError, match="conflict after normalization: data analysis"):
        extract_mentions(
            "data analysis",
            {
                "data-analysis": DATA_ANALYSIS_ID,
                "data_analysis": POSTGRESQL_ID,
            },
        )
