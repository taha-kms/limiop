"""Deterministic, longest-first extraction from a caller-owned vocabulary."""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

_SEPARATORS = re.compile(r"[\s_\-\u2010-\u2015]+")
_SURROUNDING_PUNCTUATION = " \t\r\n.,;:!?()[]{}\"'"
_TOKEN = re.compile(r"[^\W_](?:[^\W_]|[+#]|[./](?=[^\W_]))*", re.UNICODE)
_MISSING = object()

type Vocabulary = Mapping[str, UUID | None]
type _VocabularyEntry = tuple[str, UUID | None]


@dataclass(frozen=True, slots=True)
class Mention:
    """One vocabulary phrase found in source text.

    Offsets use Python's half-open string convention: ``start`` is inclusive
    and ``end`` is exclusive. ``surface_form`` is always exactly
    ``text[start:end]``.
    """

    surface_form: str
    normalized_form: str
    start: int
    end: int
    concept_id: UUID | None

    @property
    def span(self) -> tuple[int, int]:
        """Return the half-open source span."""
        return self.start, self.end

    @property
    def resolved(self) -> bool:
        """Whether this mention names exactly one caller-supplied concept."""
        return self.concept_id is not None


@dataclass(frozen=True, slots=True)
class _Token:
    value: str
    start: int
    end: int


def _normalize_surface_form(value: str) -> str:
    compatible = unicodedata.normalize("NFKC", value).casefold()
    unpunctuated = compatible.strip(_SURROUNDING_PUNCTUATION)
    return _SEPARATORS.sub(" ", unpunctuated).strip()


def _positioned_tokens(text: str) -> tuple[_Token, ...]:
    return tuple(
        _Token(
            value=_normalize_surface_form(match.group(0)),
            start=match.start(),
            end=match.end(),
        )
        for match in _TOKEN.finditer(text)
    )


def _vocabulary_entries(vocabulary: Vocabulary) -> dict[tuple[str, ...], _VocabularyEntry]:
    entries: dict[tuple[str, ...], _VocabularyEntry] = {}
    for surface_form, concept_id in vocabulary.items():
        normalized = _normalize_surface_form(surface_form)
        tokens = tuple(token.value for token in _positioned_tokens(normalized))
        if not tokens:
            raise ValueError("vocabulary surface forms must contain a term")

        matching_form = " ".join(tokens)
        previous = entries.get(tokens, _MISSING)
        entry = (matching_form, concept_id)
        if previous is not _MISSING and previous != entry:
            raise ValueError(
                f"vocabulary surface forms conflict after normalization: {matching_form}"
            )
        entries[tokens] = entry
    return entries


def _overlaps(span: tuple[int, int], other: tuple[int, int]) -> bool:
    return span[0] < other[1] and other[0] < span[1]


def extract_mentions(text: str, vocabulary: Vocabulary) -> tuple[Mention, ...]:
    """Return non-overlapping vocabulary mentions in source order.

    Vocabulary phrases are normalized for matching, while result surfaces and
    offsets always refer to the original text. Longer phrases win when two
    candidates overlap. A ``None`` mapping value represents a recognized but
    unresolved phrase; the extractor never guesses or loads a concept.
    """
    entries = _vocabulary_entries(vocabulary)
    tokens = _positioned_tokens(text)
    if not entries or not tokens:
        return ()

    found: list[Mention] = []
    taken: list[tuple[int, int]] = []
    longest = max(len(term) for term in entries)
    for size in range(longest, 0, -1):
        for index in range(len(tokens) - size + 1):
            piece = tokens[index : index + size]
            entry = entries.get(tuple(token.value for token in piece))
            if entry is None:
                continue

            start, end = piece[0].start, piece[-1].end
            span = (start, end)
            if any(_overlaps(span, previous) for previous in taken):
                continue

            normalized_form, concept_id = entry
            taken.append(span)
            found.append(
                Mention(
                    surface_form=text[start:end],
                    normalized_form=normalized_form,
                    start=start,
                    end=end,
                    concept_id=concept_id,
                )
            )

    return tuple(sorted(found, key=lambda mention: mention.span))
