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


def test_committed_gold_label_resolution_result_is_reproducible() -> None:
    result = run_measurement()

    assert result["vocabulary_version"] == "2026.08.25.1"
    assert result["gold_mentions"] == 2059
    assert result["resolved_mentions"] == 455
    assert result["rate"] == pytest.approx(0.220981)


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
