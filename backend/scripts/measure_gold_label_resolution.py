"""Measure exact gold-label resolution through a published alias table.

This is deliberately not the span-overlap recall used to compare the Phase B
vocabulary arms. The committed gold set contains annotator labels but not the
posting text needed to reproduce those span matches.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from app.modules.skills.resolution import DEFAULT_VOCABULARY_VERSION, load_resolver

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD_SET = REPOSITORY_ROOT / "docs/skill-model-measurement/gold-set.json"


class GoldMention(BaseModel):
    """The part of a committed gold mention needed by this measurement."""

    labels: tuple[str, ...] = Field(min_length=1)


class GoldSet(BaseModel):
    """The committed gold-set envelope."""

    gold: tuple[GoldMention, ...]


@dataclass(frozen=True, slots=True)
class GoldLabelResolutionResult:
    """Counts behind the gold-label resolution rate."""

    vocabulary_version: str
    gold_mentions: int
    resolved_mentions: int

    @property
    def rate(self) -> float:
        return self.resolved_mentions / self.gold_mentions if self.gold_mentions else 0.0


def measure_gold_label_resolution(
    gold_path: Path,
    vocabulary_version: str = DEFAULT_VOCABULARY_VERSION,
) -> GoldLabelResolutionResult:
    """Count mentions for which at least one recorded label resolves exactly."""
    gold_set = GoldSet.model_validate_json(gold_path.read_text(encoding="utf-8"))
    resolver = load_resolver(vocabulary_version)
    resolved_mentions = sum(
        any(resolver.resolve(label).concepts for label in mention.labels)
        for mention in gold_set.gold
    )
    return GoldLabelResolutionResult(
        vocabulary_version=vocabulary_version,
        gold_mentions=len(gold_set.gold),
        resolved_mentions=resolved_mentions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure exact annotator-label resolution through a published alias table."
    )
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD_SET)
    parser.add_argument("--vocabulary-version", default=DEFAULT_VOCABULARY_VERSION)
    args = parser.parse_args()

    result = measure_gold_label_resolution(args.gold, args.vocabulary_version)
    print(
        json.dumps(
            {
                "metric": "gold-label resolution rate",
                "vocabulary_version": result.vocabulary_version,
                "gold_mentions": result.gold_mentions,
                "resolved_mentions": result.resolved_mentions,
                "rate": round(result.rate, 6),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
