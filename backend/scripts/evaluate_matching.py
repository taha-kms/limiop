"""Print the skill-overlap baseline's score against the committed corpus.

A thin front for `app.modules.matching.evaluation`, which holds the metrics.
The numbers it prints are the gate every later matcher is compared against.
"""

import argparse
import json
from pathlib import Path

from app.modules.matching.evaluation import evaluate, load_corpus

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = REPOSITORY_ROOT / "docs/matching-evaluation/corpus.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    arguments = parser.parse_args()

    print(json.dumps(evaluate(load_corpus(arguments.corpus)), indent=2))


if __name__ == "__main__":
    main()
