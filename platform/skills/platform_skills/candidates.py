"""Proposing terms that look like skills but resolve to no concept.

The extractor matches a vocabulary and cannot see a term outside it, so the
observation inbox it feeds has stayed structurally empty since it was built.
Something has to propose the terms the vocabulary does not already contain, and
that is what this is.

The rule, stated so it can be argued with
-----------------------------------------

A candidate is a run of one to four tokens that reads like a named thing:

- **Capitalised runs.** `Kubernetes`, `Apache Kafka`, `Amazon Web Services`.
  Job postings capitalise the technologies they name and lowercase the prose
  around them, which is the cheapest true signal in the text.
- **Tokens carrying technical punctuation.** `C++`, `Node.js`, `CI/CD`,
  `.NET`. These are never ordinary words and are routinely lowercase.

A run that starts a sentence is not taken from its first token alone, because
every sentence capitalises its first word and treating that as a signal would
propose the first word of every sentence in the catalogue.

Where capitalisation carries no information
-------------------------------------------

German capitalises every noun, so in a German posting the capitalisation signal
is grammar rather than naming — the first attempt proposed `Erfahrung`,
`Aufgaben`, and `Bereich` across a hundred employers each. About a quarter of
this catalogue is German.

Rather than detect the language, which needs a dependency this package refuses,
the text is asked how much it capitalises. Measured over 1,252 stored postings:
German-looking ones capitalise a median 0.442 of their word tokens against
0.134 for English, and the two do not overlap — English reaches 0.179 at its
ninetieth percentile while German is already at 0.354 at its tenth. Above
`GRAMMATICAL_CAPITALISATION`, only the punctuation signal is used, so `Node.js`
and `CI/CD` are still proposed and `Erfahrung` is not.

Nothing here decides whether a candidate is a skill. It proposes, the caller
records, and the promotion decision happens later against accumulated evidence
— which is the whole reason the inbox exists.

Pure, like the rest of this package: no vocabulary, no database, no network.
"""

import re
from collections.abc import Iterator, Set
from dataclasses import dataclass

MAXIMUM_TOKENS = 4

# The share of word tokens above which capitalisation is grammar rather than
# naming. Set between the two populations rather than at either edge: English
# postings reach 0.179 at p90, German ones start at 0.354 at p10.
GRAMMATICAL_CAPITALISATION = 0.25

# Below this many words the share is noise rather than a measurement. A single
# sentence naming two technologies is already at 0.4, so a short description
# would be gated out for looking like German when it is a short description.
MEASURABLE_WORDS = 30

# A token that is either capitalised, or carries punctuation no ordinary word
# does. The character classes are explicit rather than \w so that a digit-only
# token cannot start a run: `2024 Berlin` is a year and a city, not a term.
_CAPITALISED = r"[A-ZÀ-Þ][\wÀ-ɏ]*"
_PUNCTUATED = r"[A-Za-z][\w]*(?:[+#./][\w+#]+)+"
_TOKEN = re.compile(rf"{_PUNCTUATED}|{_CAPITALISED}|[\wÀ-ɏ]+")

# Where a sentence ends, so the token after it is not read as a name.
_SENTENCE_END = re.compile(r"[.!?:;\n]\s*$|^\s*$|[)\]]\s*$")

# Words that are capitalised for grammar rather than because they name
# something. Left deliberately short: every entry is a judgment, and a long list
# is a content filter wearing a stopword list's clothes.
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "but",
        "by",
        "for",
        "from",
        "if",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "our",
        "the",
        "to",
        "we",
        "with",
        "you",
        "your",
        "der",
        "die",
        "das",
        "und",
        "mit",
        "für",
        "von",
        "im",
        "wir",
        "du",
    }
)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One proposed term and where it was found."""

    surface_form: str
    start: int
    end: int

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)


_WORD = re.compile(r"[A-Za-zÀ-ɏ][\wÀ-ɏ]*")


def capitalisation_density(text: str) -> float:
    """The share of word tokens that begin with a capital.

    Zero for anything too short to measure, so the gate does not fire on a
    fragment. `Experience with Kubernetes is required.` is 0.4 and would
    otherwise be read as a language that capitalises its nouns.
    """
    words = _WORD.findall(text)
    if len(words) < MEASURABLE_WORDS:
        return 0.0
    return sum(1 for word in words if word[0].isupper()) / len(words)


def _looks_named(token: str, *, capitalisation_means_naming: bool) -> bool:
    if token.casefold() in STOPWORDS:
        return False
    if re.fullmatch(_PUNCTUATED, token):
        return True
    if not capitalisation_means_naming:
        return False
    return bool(re.fullmatch(_CAPITALISED, token)) and not token.isdigit()


def _tokens(text: str) -> list[re.Match[str]]:
    return list(_TOKEN.finditer(text))


def _starts_a_sentence(text: str, match: re.Match[str]) -> bool:
    return bool(_SENTENCE_END.search(text[: match.start()][-40:]))


def propose(text: str) -> Iterator[Candidate]:
    """Every run of named-looking tokens, longest first at each position.

    Overlapping runs are all proposed. A posting naming `Amazon Web Services`
    proposes that and `Amazon`, because which of them is the skill is exactly
    the question the accumulated evidence is meant to answer, and choosing here
    would answer it with a guess.
    """
    matches = _tokens(text)
    naming = capitalisation_density(text) <= GRAMMATICAL_CAPITALISATION
    for index, match in enumerate(matches):
        if not _looks_named(match.group(0), capitalisation_means_naming=naming):
            continue
        # A sentence's first word is capitalised by grammar. It may still begin
        # a real term, so the run is kept only when something follows it.
        first_is_grammatical = _starts_a_sentence(text, match)
        run: list[re.Match[str]] = []
        for candidate in matches[index : index + MAXIMUM_TOKENS]:
            if not _looks_named(candidate.group(0), capitalisation_means_naming=naming):
                break
            # Tokens must be adjacent in the text, separated by whitespace only.
            if run and text[run[-1].end() : candidate.start()].strip():
                break
            run.append(candidate)
            if first_is_grammatical and len(run) == 1:
                continue
            yield Candidate(
                surface_form=text[run[0].start() : run[-1].end()],
                start=run[0].start(),
                end=run[-1].end(),
            )


def unknown_terms(text: str, known: Set[str]) -> Iterator[Candidate]:
    """Proposed terms the vocabulary does not already contain.

    `known` holds normalized surface forms. A term the vocabulary resolves is
    not a candidate: it is a skill, and the extractor already recorded it.
    """
    for candidate in propose(text):
        if " ".join(candidate.surface_form.split()).casefold() not in known:
            yield candidate
