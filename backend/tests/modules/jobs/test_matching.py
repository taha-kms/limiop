from typing import Any

import pytest

from app.modules.jobs.matching import (
    MATCH_KEY_VERSION,
    MINIMUM_TEXT_OVERLAP,
    city_names,
    match_key,
    match_key_of,
    reads_the_same,
    same_place,
    text_overlap,
)
from app.modules.jobs.schemas import NormalizedJob


def job(**overrides: Any) -> NormalizedJob:
    payload: dict[str, Any] = {
        "company": {"display_name": "Acme GmbH"},
        "title": "Senior Data Engineer",
        "description": "Build reliable data pipelines.",
        "location": "Berlin",
        "application_url": "https://acme.example.com/jobs/1",
        "provenance": {
            "source_key": "arbeitnow",
            "source_job_id": "1",
            "source_url": "https://arbeitnow.example.com/1",
        },
    }
    payload.update(overrides)
    return NormalizedJob.model_validate(payload)


class TestMatchKey:
    def test_the_key_carries_the_rules_that_made_it(self) -> None:
        assert match_key(job()).startswith(f"{MATCH_KEY_VERSION}:")

    def test_the_same_job_always_produces_the_same_key(self) -> None:
        assert match_key(job()) == match_key(job())

    def test_the_location_is_not_part_of_the_key(self) -> None:
        """Every confirmed cross-source duplicate described its location differently."""
        assert match_key(job(location="London")) == match_key(job(location="London, UK"))
        assert match_key(job(location=None)) == match_key(job(location="Berlin"))

    def test_the_description_is_not_part_of_the_key(self) -> None:
        """Employers reword a posting without reposting it."""
        assert match_key(job(description="One wording.")) == match_key(
            job(description="Another wording entirely.")
        )

    def test_a_different_role_is_a_different_key(self) -> None:
        assert match_key(job(title="Data Engineer")) != match_key(job(title="Product Designer"))

    def test_a_different_employer_is_a_different_key(self) -> None:
        assert match_key(job()) != match_key(job(company={"display_name": "Globex AG"}))

    @pytest.mark.parametrize(
        "title",
        ["Data Engineer (m/w/d)", "Data Engineer (all genders)", "  data   engineer  "],
    )
    def test_a_title_written_differently_is_the_same_role(self, title: str) -> None:
        assert match_key(job(title=title)) == match_key(job(title="Data Engineer"))

    def test_the_parts_cannot_run_into_each_other(self) -> None:
        """Without a separator, ("ab","c") and ("a","bc") would hash alike."""
        assert match_key_of("ab", "c") != match_key_of("a", "bc")


class TestCityNames:
    @pytest.mark.parametrize(
        ("location", "expected"),
        [
            pytest.param("London", {"london"}, id="a city alone"),
            pytest.param("London, UK", {"london"}, id="country dropped"),
            pytest.param("Berlin, Berlin, Germany", {"berlin"}, id="region dropped"),
            pytest.param(
                "Berlin, Berlin; München, Bavaria",
                {"berlin", "münchen"},
                id="several places",
            ),
            pytest.param(
                "Freiburg (Germany), Berlin (Germany)",
                {"berlin", "freiburg"},
                id="each place naming its country",
            ),
            pytest.param("Remote, France", {"france"}, id="an arrangement then a place"),
        ],
    )
    def test_a_location_names_its_cities(self, location: str, expected: set[str]) -> None:
        assert city_names(location) == expected

    @pytest.mark.parametrize(
        "location",
        [None, "", "Remote", "  ", "Hybrid", "Homeoffice"],
    )
    def test_an_arrangement_is_not_a_place(self, location: str | None) -> None:
        assert city_names(location) == frozenset()


class TestSamePlace:
    def test_the_same_city_written_two_ways_is_one_place(self) -> None:
        assert same_place("London", "London, UK")
        assert same_place("Berlin, Berlin", "Berlin, Berlin, Germany")

    def test_different_cities_are_different_places(self) -> None:
        """One employer runs the same role in four countries, and those are four jobs."""
        assert not same_place("Seoul, South Korea", "Tokyo, Japan")
        assert not same_place("Remote, France", "Remote, Spain")

    def test_a_side_naming_no_city_contradicts_nothing(self) -> None:
        assert same_place("Remote", "Remote, United Kingdom")
        assert same_place(None, "Berlin")

    def test_a_subset_is_not_the_same_place(self) -> None:
        """Measured: allowing it found three more duplicates and lost one job."""
        assert not same_place("Costa Mesa", "Costa Mesa; Washington")


class TestReadsTheSame:
    def test_the_same_posting_from_two_sources_reads_the_same(self) -> None:
        assert reads_the_same(
            "Build reliable data pipelines here.", "Build reliable data pipelines here."
        )

    def test_a_different_posting_does_not(self) -> None:
        assert not reads_the_same(
            "Manage the accounts payable ledger every month.",
            "Design distributed storage systems in Rust.",
        )

    def test_an_empty_description_matches_nothing(self) -> None:
        assert text_overlap("", "anything at all") == 0.0
        assert not reads_the_same("", "anything at all")

    def test_the_threshold_sits_between_what_was_measured(self) -> None:
        """Confirmed duplicates reached 0.966; measured wrong merges reached 0.82."""
        assert 0.82 < MINIMUM_TEXT_OVERLAP < 0.966
