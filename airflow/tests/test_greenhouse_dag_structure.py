"""Structure tests for the scheduled Greenhouse ingestion DAG."""

from datetime import timedelta
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DAG

DAGS_DIR = Path(__file__).parents[1] / "dags"
DAG_ID = "greenhouse_ingestion"


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    # Airflow 3.3 dropped include_examples; see test_dag_structure.py.
    return DagBag(dag_folder=str(DAGS_DIR))


def test_the_greenhouse_ingestion_dag_is_registered(dagbag: DagBag) -> None:
    assert DAG_ID in dagbag.dags


def test_the_greenhouse_dag_is_scheduled_independently(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    assert dag.schedule == "30 * * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1


def test_greenhouse_failure_behavior_is_explicit(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]
    task = dag.get_task("ingest")

    assert task.retries == 2
    assert task.retry_delay == timedelta(minutes=5)
    assert task.execution_timeout == timedelta(minutes=15)


def test_the_greenhouse_dag_stays_a_single_thin_task(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    assert [task.task_id for task in dag.tasks] == ["ingest"]


def test_the_greenhouse_dag_delegates_to_reusable_application_code() -> None:
    source = (DAGS_DIR / f"{DAG_ID}.py").read_text()

    assert "from job_ingestion.greenhouse import ingest_greenhouse" in source
