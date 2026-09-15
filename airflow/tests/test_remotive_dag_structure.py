"""Structure tests that keep the Remotive DAG file thin.

These load the DAG through Airflow's own DagBag, so an import error here means
the DAG would also fail to load in a real Airflow deployment.
"""

from datetime import timedelta
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DAG

DAGS_DIR = Path(__file__).parents[1] / "dags"
DAG_ID = "remotive_ingestion"


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR))


def test_every_dag_imports_cleanly(dagbag: DagBag) -> None:
    assert dagbag.import_errors == {}


def test_the_ingestion_dag_is_registered(dagbag: DagBag) -> None:
    assert DAG_ID in dagbag.dags


def test_the_dag_is_scheduled_and_does_not_backfill(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    assert dag.schedule == "20 */6 * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1


def test_the_schedule_fires_four_times_a_day(dagbag: DagBag) -> None:
    """Remotive's own API notice asks callers to poll at most four times a
    day; the hour field `*/6` is what turns the cron into exactly that
    ceiling, computed here rather than merely asserted."""
    dag: DAG = dagbag.dags[DAG_ID]
    minute, hour, *_rest = str(dag.schedule).split()

    assert minute == "20"
    assert hour == "*/6"

    step = int(hour.removeprefix("*/"))
    hours_in_a_day = 24
    occurrences_per_day = hours_in_a_day // step

    assert occurrences_per_day == 4


def test_failure_behavior_is_explicit(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]
    task = dag.get_task("ingest")

    assert task.retries == 2
    assert task.retry_delay == timedelta(minutes=5)
    assert task.execution_timeout == timedelta(minutes=15)


def test_the_dag_stays_a_single_thin_task(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    assert [task.task_id for task in dag.tasks] == ["ingest"]


def test_the_dag_delegates_to_reusable_application_code() -> None:
    source = (DAGS_DIR / f"{DAG_ID}.py").read_text()

    assert "from job_ingestion.remotive import ingest_remotive" in source
