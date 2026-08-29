import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MEASUREMENT_SCRIPT = BACKEND_ROOT / "scripts/measure_gold_label_resolution.py"


def run_measurement(*arguments: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(MEASUREMENT_SCRIPT), *arguments],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return cast(dict[str, object], json.loads(completed.stdout))


@pytest.mark.parametrize("vocabulary_version", ["2026.08.25.1", "2026.08.28.1", "2026.08.29.1"])
def test_committed_gold_label_resolution_result_is_reproducible(vocabulary_version: str) -> None:
    """The 2026-08-28 audit removed 50 surface forms and cost none of these.

    Pinned per version rather than left on the default so that publishing a new
    alias table cannot silently rewrite what the committed measurement says.
    """
    result = run_measurement("--vocabulary-version", vocabulary_version)

    assert result["vocabulary_version"] == vocabulary_version
    assert result["gold_mentions"] == 2059
    assert result["resolved_mentions"] == 455
    assert result["rate"] == pytest.approx(0.220981)


def test_the_compound_disciplines_resolve_labels_the_bare_head_could_not() -> None:
    """35 mentions, all of them a modifier the head never carried."""
    result = run_measurement("--vocabulary-version", "2026.08.29.2")

    assert result["resolved_mentions"] == 490
    assert result["rate"] == pytest.approx(0.23798)


def test_a_mention_resolves_when_any_recorded_annotator_label_resolves(
    tmp_path: Path,
) -> None:
    gold_path = tmp_path / "gold-set.json"
    gold_path.write_text(
        json.dumps(
            {
                "gold": [
                    {"labels": ["unmapped annotator wording", "deep learning"]},
                    {"labels": ["unmapped annotator wording"]},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_measurement("--gold", str(gold_path))

    assert result["gold_mentions"] == 2
    assert result["resolved_mentions"] == 1
    assert result["rate"] == 0.5
