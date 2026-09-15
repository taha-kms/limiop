"""Structure tests that keep the Jobicy DAG file thin.

These load the DAG through Airflow's own DagBag, so an import error here means
the DAG would also fail to load in a real Airflow deployment.
"""

from datetime import timedelta
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DAG

DAGS_DIR = Path(__file__).parents[1] / "dags"
DAG_ID = "jobicy_ingestion"


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR))


def test_the_ingestion_dag_is_registered(dagbag: DagBag) -> None:
    assert DAG_ID in dagbag.dags


def test_the_dag_is_scheduled_and_does_not_backfill(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    # Offset from Arbeitnow's :00 so the two providers do not compete for the
    # same minute.
    assert dag.schedule == "15 * * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1


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

    assert "from job_ingestion.jobicy import ingest_jobicy" in source
