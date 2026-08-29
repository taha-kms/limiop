"""Proposing terms that look like skills but resolve to no concept."""

import time

import pytest

from platform_skills.candidates import (
    GRAMMATICAL_CAPITALISATION,
    capitalisation_density,
    propose,
    unknown_terms,
)


def forms(text: str) -> set[str]:
    return {" ".join(c.surface_form.split()) for c in propose(text)}


def test_a_capitalised_technology_is_proposed() -> None:
    assert "Kubernetes" in forms("Experience with Kubernetes is required.")


def test_a_multi_word_name_is_proposed_whole_and_in_parts() -> None:
    """Which of them is the skill is what the accumulated evidence answers."""
    found = forms("We run on Amazon Web Services daily.")

    assert {"Amazon Web Services", "Amazon Web", "Amazon"} <= found


def test_a_run_stops_at_a_lowercase_word() -> None:
    assert "Amazon Web" not in forms("Amazon and Web are separate.")


def test_technical_punctuation_is_proposed_even_lowercase() -> None:
    found = forms("Comfortable with node.js and ci/cd pipelines.")

    assert "node.js" in found
    assert "ci/cd" in found


def test_a_run_is_bounded_so_a_capitalised_sentence_is_not_one_term() -> None:
    text = "Alpha Beta Gamma Delta Epsilon"

    assert max(len(form.split()) for form in forms(text)) == 4


def test_the_first_word_of_a_sentence_is_not_a_term_on_its_own() -> None:
    """Every sentence capitalises it, so taking it would propose one per
    sentence in the catalogue."""
    found = forms("Kubernetes is used. Docker is too.")

    assert "Docker" not in found
    assert "Kubernetes" not in found


def test_a_sentence_opener_still_begins_a_longer_term() -> None:
    assert "Apache Kafka" in forms("We stream events. Apache Kafka runs it.")


def test_a_grammatical_word_is_not_a_term() -> None:
    assert forms("The Team And You") == {"Team"} or "And" not in forms("The Team And You")


def test_a_year_is_not_a_term() -> None:
    assert "2024" not in forms("Since 2024 we have grown.")


def test_german_text_proposes_no_nouns_because_it_capitalises_all_of_them() -> None:
    """Measured: German postings capitalise 0.44 of their words, English 0.13.

    Without this the first attempt proposed `Erfahrung`, `Aufgaben` and
    `Bereich` across a hundred employers each.
    """
    german = (
        "Deine Aufgaben umfassen die Betreuung der Systeme im Bereich Infrastruktur. "
        "Erfahrung mit Kubernetes und Docker sind von Vorteil. Wir bieten dir ein "
        "Team mit flachen Hierarchien und viel Verantwortung in deinem Bereich."
    )
    assert capitalisation_density(german) > GRAMMATICAL_CAPITALISATION

    assert "Erfahrung" not in forms(german)
    assert "Aufgaben" not in forms(german)


def test_technical_punctuation_survives_in_german_text() -> None:
    """The capitalisation signal is dropped there; the other one is not."""
    german = (
        "Deine Aufgaben umfassen die Entwicklung mit node.js im Bereich der "
        "Systeme und der Anwendungen. Erfahrung mit ci/cd und viel Verantwortung "
        "in deinem Team sind uns wichtig. Wir bieten dir ein modernes Umfeld mit "
        "flachen Hierarchien und viel Gestaltungsspielraum in deinem Bereich."
    )

    assert capitalisation_density(german) > GRAMMATICAL_CAPITALISATION
    assert "node.js" in forms(german)


def test_text_too_short_to_measure_is_not_gated() -> None:
    """One sentence naming two technologies is already at 0.4 capitalisation."""
    assert capitalisation_density("Experience with Kubernetes is required.") == 0.0


def test_english_text_stays_below_the_grammatical_threshold() -> None:
    english = (
        "You will build and maintain the services that power our product, working "
        "with a small team of engineers who care about the work they ship."
    )

    assert capitalisation_density(english) <= GRAMMATICAL_CAPITALISATION


def test_empty_text_proposes_nothing() -> None:
    assert forms("") == set()
    assert capitalisation_density("") == 0.0


def test_a_term_the_vocabulary_already_holds_is_not_a_candidate() -> None:
    """Proposing it would put the same term in both tables."""
    text = "We use Kubernetes and Terraform."
    known = {"kubernetes"}

    proposed = {" ".join(c.surface_form.split()) for c in unknown_terms(text, known)}

    assert "Kubernetes" not in proposed
    assert "Terraform" in proposed


@pytest.mark.parametrize("text", ["Kubernetes rocks", "we use node.js", ""])
def test_every_candidate_span_points_at_its_own_text(text: str) -> None:
    for candidate in propose(text):
        assert text[candidate.start : candidate.end] == candidate.surface_form


@pytest.mark.parametrize("term", ["Node.js", "CI/CD", "C++", "C#", "F#", "e.g", "and/or"])
def test_punctuated_terms_are_matched_whole(term: str) -> None:
    assert term in forms(f"We use {term} here.")


def test_the_pattern_does_not_backtrack_on_hostile_text() -> None:
    """Provider text is untrusted and this runs over every posting.

    The first pattern put `+` and `#` in both the separator class and the token
    body, so the engine could split a run two ways at every step. This input is
    the shape that exploits it.
    """
    hostile = "A" + "+#./" * 20000

    started = time.perf_counter()
    list(propose(hostile))

    assert time.perf_counter() - started < 1.0
