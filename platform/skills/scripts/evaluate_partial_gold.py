"""Score the shared extractor against the recoverable gold-posting subset."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast
from uuid import UUID

from platform_skills import Mention, Vocabulary, extract_mentions

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEXTS = REPOSITORY_ROOT / ".research/platform-skills-recovered-postings.json"
DEFAULT_GOLD = REPOSITORY_ROOT / "docs/skill-model-measurement/gold-set.json"
DEFAULT_VOCABULARY = REPOSITORY_ROOT / "backend/app/modules/skills/data/aliases.v2.json"


def _object(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return cast(dict[str, object], value)


def _array(value: object, *, context: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")
    return cast(list[object], value)


def _string(value: object, *, context: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a string")
    return value


def _integer(value: object, *, context: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{context} must be an integer")
    return value


def _read_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    return _object(value, context=str(path))


def load_texts(path: Path) -> dict[str, str]:
    document = _read_object(path)
    rows = _array(document.get("postings"), context=f"{path}: postings")
    texts: dict[str, str] = {}
    for index, value in enumerate(rows):
        row = _object(value, context=f"{path}: postings[{index}]")
        posting = _string(row.get("posting"), context=f"{path}: postings[{index}].posting")
        description = _string(
            row.get("description"), context=f"{path}: postings[{index}].description"
        )
        expected_digest = _string(
            row.get("description_sha256"),
            context=f"{path}: postings[{index}].description_sha256",
        )
        actual_digest = hashlib.sha256(description.encode()).hexdigest()
        if actual_digest != expected_digest:
            raise ValueError(f"{path}: description hash differs for {posting}")
        if posting in texts:
            raise ValueError(f"{path}: posting is duplicated: {posting}")
        texts[posting] = description
    return texts


def load_gold(path: Path, postings: set[str]) -> list[tuple[str, int, int]]:
    document = _read_object(path)
    rows = _array(document.get("gold"), context=f"{path}: gold")
    mentions: list[tuple[str, int, int]] = []
    for index, value in enumerate(rows):
        row = _object(value, context=f"{path}: gold[{index}]")
        posting = _string(row.get("posting"), context=f"{path}: gold[{index}].posting")
        if posting not in postings:
            continue
        mentions.append(
            (
                posting,
                _integer(row.get("start"), context=f"{path}: gold[{index}].start"),
                _integer(row.get("end"), context=f"{path}: gold[{index}].end"),
            )
        )
    return mentions


def load_vocabulary(path: Path) -> dict[str, UUID | None]:
    document = _read_object(path)
    rows = _array(document.get("surface_forms"), context=f"{path}: surface_forms")
    vocabulary: dict[str, UUID | None] = {}
    for index, value in enumerate(rows):
        row = _object(value, context=f"{path}: surface_forms[{index}]")
        surface_form = _string(
            row.get("surface_form"), context=f"{path}: surface_forms[{index}].surface_form"
        )
        concept_values = _array(
            row.get("concept_ids"), context=f"{path}: surface_forms[{index}].concept_ids"
        )
        concepts = tuple(
            UUID(_string(concept, context=f"{path}: surface_forms[{index}].concept_ids"))
            for concept in concept_values
        )
        vocabulary[surface_form] = concepts[0] if len(concepts) == 1 else None
    return vocabulary


def _overlaps(span: tuple[int, int], other: tuple[int, int]) -> bool:
    return span[0] < other[1] and other[0] < span[1]


def score(
    texts: dict[str, str],
    gold: list[tuple[str, int, int]],
    vocabulary: Vocabulary,
) -> dict[str, int | float | str]:
    matches: dict[str, tuple[Mention, ...]] = {
        posting: extract_mentions(text, vocabulary) for posting, text in texts.items()
    }
    found = sum(
        any(_overlaps((start, end), mention.span) for mention in matches[posting])
        for posting, start, end in gold
    )
    flat_matches = [mention for posting in texts for mention in matches[posting]]
    gold_by_posting: dict[str, list[tuple[int, int]]] = {posting: [] for posting in texts}
    for posting, start, end in gold:
        gold_by_posting[posting].append((start, end))
    on_gold = sum(
        any(_overlaps(mention.span, span) for span in gold_by_posting[posting])
        for posting in texts
        for mention in matches[posting]
    )
    return {
        "measurement": "partial sanity check",
        "recovered_postings": len(texts),
        "gold_mentions": len(gold),
        "extracted_mentions": len(flat_matches),
        "precision": round(on_gold / len(flat_matches), 4) if flat_matches else 0.0,
        "recall": round(found / len(gold), 4) if gold else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the platform-skills partial gold-set sanity check."
    )
    parser.add_argument("--texts", type=Path, default=DEFAULT_TEXTS)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--vocabulary", type=Path, default=DEFAULT_VOCABULARY)
    arguments = parser.parse_args()

    texts = load_texts(arguments.texts)
    gold = load_gold(arguments.gold, set(texts))
    vocabulary = load_vocabulary(arguments.vocabulary)
    print(json.dumps(score(texts, gold, vocabulary), indent=2))


if __name__ == "__main__":
    main()
